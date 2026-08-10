import base64
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.llm.router import ModelChoice, resolve

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class LLMTruncatedError(RuntimeError):
    """Raised when the model hits max_completion_tokens (finish_reason ==
    "length") before finishing its response. A truncated completion is not
    partial-but-usable — for a structured call the JSON is very likely
    unparseable, and for free text there's no way to tell how much of the
    "visible" answer never got emitted versus how much was spent on hidden
    reasoning tokens. Content is discarded rather than returned, on purpose:
    a 4000-token cap that silently yielded an empty report is what caused
    this class to exist (see the Phase 1 smoke test writeup)."""

    def __init__(self, model: str, max_completion_tokens: int, output_tokens: int):
        self.model = model
        self.max_completion_tokens = max_completion_tokens
        self.output_tokens = output_tokens
        super().__init__(
            f"LLM response truncated: model={model} max_completion_tokens={max_completion_tokens} "
            f"consumed_output_tokens={output_tokens} (finish_reason=length)"
        )


@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int
    model: str


@dataclass
class LLMStructuredResponse:
    parsed: Any  # instance of the `schema` passed to generate_structured
    input_tokens: int
    output_tokens: int
    model: str


@dataclass
class EmbedResponse:
    vectors: list[list[float]]
    input_tokens: int
    model: str


class LLMStream:
    """Async iterator over content deltas from a streaming chat completion
    (`LLMProvider.generate_stream`). Each `__anext__` returns the next
    non-empty text delta. Once the underlying stream is exhausted, `.response`
    is populated with an `LLMResponse` shaped exactly like `generate()`'s
    return value, so a caller that needs the full text/usage after streaming
    doesn't have to reassemble it by hand — mirrors the accumulate-then-use
    pattern OpenAI's own streaming helpers use.

    Requires `stream_options={"include_usage": True}` on the underlying call
    (set by `generate_stream`) — without it, OpenAI's streaming API returns no
    token usage at all, and the tracer's cost accounting would silently zero
    out every streamed call."""

    def __init__(self, chunks: AsyncIterator[Any], model: str, max_completion_tokens: int):
        self._chunks = chunks
        self._model = model
        self._max_completion_tokens = max_completion_tokens
        self._buffer: list[str] = []
        self._input_tokens = 0
        self._output_tokens = 0
        self._finish_reason: str | None = None
        self.response: LLMResponse | None = None

    def __aiter__(self) -> "LLMStream":
        return self

    async def __anext__(self) -> str:
        while True:
            try:
                chunk = await self._chunks.__anext__()
            except StopAsyncIteration:
                self._finalize()
                raise

            # The include_usage final chunk carries usage but an empty
            # `choices` array — a different shape from every other chunk.
            if chunk.usage is not None:
                self._input_tokens = chunk.usage.prompt_tokens
                self._output_tokens = chunk.usage.completion_tokens
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            if choice.finish_reason is not None:
                self._finish_reason = choice.finish_reason
            delta = choice.delta.content
            if delta:
                self._buffer.append(delta)
                return delta
            # empty delta (e.g. the role-only first chunk) — keep pulling

    def _finalize(self) -> None:
        content = "".join(self._buffer)
        if self._finish_reason == "length":
            # Same discard-on-truncation contract as generate() — see
            # LLMTruncatedError's docstring. Chunks already streamed to any
            # WS subscriber can't be un-sent, but the node's own return value
            # (and therefore the persisted report) never gets the truncated
            # content.
            raise LLMTruncatedError(self._model, self._max_completion_tokens, self._output_tokens)
        self.response = LLMResponse(
            content=content,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            model=self._model,
        )


class LLMProvider:
    """Provider-agnostic LLM interface (PRD §13) — no OpenAI-specific type may
    leak into graph/nodes/*. Model selection, reasoning-effort, and the
    per-task completion-token cap are resolved from llm.router, never
    hardcoded in a node."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._client = AsyncOpenAI(api_key=self._settings.OPENAI_API_KEY)
        # Only constructed when a key is present — router.resolve() already
        # never returns provider="groq" without one, but _client_for's guard
        # below is what makes that a defensive invariant rather than an
        # assumption baked in twice.
        self._groq_client = (
            AsyncOpenAI(base_url=self._settings.GROQ_BASE_URL, api_key=self._settings.GROQ_API_KEY)
            if self._settings.GROQ_API_KEY
            else None
        )

    def _build_messages(self, system: str | None, user: str) -> list[dict[str, str]]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        return messages

    def _extra_kwargs(self, choice: ModelChoice) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"max_completion_tokens": choice.max_completion_tokens}
        if choice.reasoning_effort is not None:
            kwargs["reasoning_effort"] = choice.reasoning_effort
        return kwargs

    def _client_for(self, choice: ModelChoice) -> AsyncOpenAI:
        if choice.provider == "groq":
            if self._groq_client is None:
                raise RuntimeError("ModelChoice.provider is 'groq' but GROQ_API_KEY is not set")
            return self._groq_client
        return self._client

    def _openai_fallback(self, choice: ModelChoice) -> ModelChoice:
        """Groq's free tier in particular has a tight per-minute token cap
        (see PARALLELIZATION_PLAN.md-adjacent cost discussion) — a 429 mid-run
        should degrade to the OpenAI reasoning-tier model for that one call,
        not fail the run. reasoning_effort/max_completion_tokens carry over
        unchanged since gpt-oss-120b and OpenAI's reasoning tier accept the
        same low/medium/high/none values."""
        return ModelChoice(
            model=self._settings.OPENAI_MODEL_REASONING,
            tier=choice.tier,
            reasoning_effort=choice.reasoning_effort,
            max_completion_tokens=choice.max_completion_tokens,
            provider="openai",
        )

    async def generate(self, task: str, *, system: str | None = None, user: str) -> LLMResponse:
        choice = resolve(task, self._settings)
        try:
            completion = await self._client_for(choice).chat.completions.create(
                model=choice.model,
                messages=self._build_messages(system, user),
                **self._extra_kwargs(choice),
            )
        except Exception as exc:
            if choice.provider != "groq":
                raise
            logger.warning("generate[%s]: Groq call failed (%s), falling back to OpenAI", task, exc)
            choice = self._openai_fallback(choice)
            completion = await self._client.chat.completions.create(
                model=choice.model,
                messages=self._build_messages(system, user),
                **self._extra_kwargs(choice),
            )
        finish_reason = completion.choices[0].finish_reason
        usage = completion.usage
        output_tokens = usage.completion_tokens if usage else 0
        if finish_reason == "length":
            raise LLMTruncatedError(choice.model, choice.max_completion_tokens, output_tokens)
        return LLMResponse(
            content=completion.choices[0].message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=output_tokens,
            model=choice.model,
        )

    async def generate_stream(self, task: str, *, system: str | None = None, user: str) -> LLMStream:
        """Streaming counterpart to `generate()` — used only by synthesizer
        today, so the report can emit `report_chunk` WS frames as tokens
        arrive instead of after one blocking call. No streaming variant of
        `generate_structured` exists; forced-JSON schema calls aren't
        rendered token-by-token in the UI, so there's no reason to stream them."""
        choice = resolve(task, self._settings)
        try:
            stream = await self._client_for(choice).chat.completions.create(
                model=choice.model,
                messages=self._build_messages(system, user),
                stream=True,
                stream_options={"include_usage": True},
                **self._extra_kwargs(choice),
            )
        except Exception as exc:
            if choice.provider != "groq":
                raise
            logger.warning("generate_stream[%s]: Groq call failed (%s), falling back to OpenAI", task, exc)
            choice = self._openai_fallback(choice)
            stream = await self._client.chat.completions.create(
                model=choice.model,
                messages=self._build_messages(system, user),
                stream=True,
                stream_options={"include_usage": True},
                **self._extra_kwargs(choice),
            )
        return LLMStream(stream, model=choice.model, max_completion_tokens=choice.max_completion_tokens)

    async def generate_structured(
        self, task: str, *, system: str | None = None, user: str, schema: type[T]
    ) -> LLMStructuredResponse:
        choice = resolve(task, self._settings)
        try:
            completion = await self._client_for(choice).chat.completions.parse(
                model=choice.model,
                messages=self._build_messages(system, user),
                response_format=schema,
                **self._extra_kwargs(choice),
            )
        except Exception as exc:
            if choice.provider != "groq":
                raise
            logger.warning("generate_structured[%s]: Groq call failed (%s), falling back to OpenAI", task, exc)
            choice = self._openai_fallback(choice)
            completion = await self._client.chat.completions.parse(
                model=choice.model,
                messages=self._build_messages(system, user),
                response_format=schema,
                **self._extra_kwargs(choice),
            )
        finish_reason = completion.choices[0].finish_reason
        usage = completion.usage
        output_tokens = usage.completion_tokens if usage else 0
        if finish_reason == "length":
            raise LLMTruncatedError(choice.model, choice.max_completion_tokens, output_tokens)

        message = completion.choices[0].message
        if message.parsed is None:
            raise ValueError(f"structured output parse failed for {schema.__name__}: {message.refusal}")
        return LLMStructuredResponse(
            parsed=message.parsed,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=output_tokens,
            model=choice.model,
        )

    async def embed(self, texts: list[str]) -> EmbedResponse:
        """No task/tier routing — there's only one embedding model, unlike
        generate/generate_structured. Returns [] vectors for [] input rather
        than making a pointless API call."""
        if not texts:
            return EmbedResponse(vectors=[], input_tokens=0, model=self._settings.OPENAI_EMBEDDING_MODEL)
        response = await self._client.embeddings.create(
            model=self._settings.OPENAI_EMBEDDING_MODEL,
            input=texts,
        )
        vectors = [item.embedding for item in response.data]
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        return EmbedResponse(vectors=vectors, input_tokens=input_tokens, model=self._settings.OPENAI_EMBEDDING_MODEL)

    async def generate_image(self, prompt: str) -> bytes:
        """Flat per-image pricing (app.config.IMAGE_COST_PER_IMAGE_USD), not
        token-based — callers apply that cost via NodeResult.cost_override
        rather than PRICING/estimate_cost(), which only knows how to price
        input/output tokens. GPT image models always return base64 (no
        response_format param — that's DALL-E-2/3 only)."""
        response = await self._client.images.generate(
            model=self._settings.OPENAI_IMAGE_MODEL,
            prompt=prompt,
            quality=self._settings.IMAGE_QUALITY,
            size="1024x1024",
            n=1,
        )
        return base64.b64decode(response.data[0].b64_json)
