from dataclasses import dataclass
from typing import Any, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.llm.router import ModelChoice, resolve

T = TypeVar("T", bound=BaseModel)


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


class LLMProvider:
    """Provider-agnostic LLM interface (PRD §13) — no OpenAI-specific type may
    leak into graph/nodes/*. Model selection, reasoning-effort, and the
    per-task completion-token cap are resolved from llm.router, never
    hardcoded in a node."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._client = AsyncOpenAI(api_key=self._settings.OPENAI_API_KEY)

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

    async def generate(self, task: str, *, system: str | None = None, user: str) -> LLMResponse:
        choice = resolve(task, self._settings)
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

    async def generate_structured(
        self, task: str, *, system: str | None = None, user: str, schema: type[T]
    ) -> LLMStructuredResponse:
        choice = resolve(task, self._settings)
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
