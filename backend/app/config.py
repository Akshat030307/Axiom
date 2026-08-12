from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Keys
    OPENAI_API_KEY: str
    SEARCH_API_KEY: str
    SEMANTIC_SCHOLAR_API_KEY: str = ""
    OPENALEX_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    # Models
    OPENAI_MODEL_REASONING: str
    OPENAI_MODEL_FAST: str
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    # "openai" (default) or "groq" — switches every reasoning-tier task
    # (planning, synthesis, figure/illustration planning, contradiction
    # resolution) to Groq's hosted inference. Fast-tier tasks and embeddings
    # are unaffected regardless of this setting — Groq has no embedding API,
    # and the fast tier's tasks weren't the expensive ones this was meant to
    # address. Has no effect if GROQ_API_KEY is empty (see LLMProvider).
    REASONING_PROVIDER: str = "openai"
    # gpt-oss-120b specifically, not "any Groq model" — it's OpenAI's own
    # open-weight reasoning model (so the existing reasoning_effort plumbing
    # applies unchanged) and one of only two Groq-hosted models that support
    # the full low/medium/high range this codebase already passes; most
    # other Groq models only accept none/default and would 400 otherwise.
    GROQ_MODEL_REASONING: str = "openai/gpt-oss-120b"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    EMBEDDING_DIM: int = 1536
    SEARCH_PROVIDER: str = "tavily"

    # Infrastructure
    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"
    FIGURES_DIR: str = "/data/figures"
    EXPORTS_DIR: str = "/data/exports"

    # Auth
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 15
    REFRESH_TOKEN_DAYS: int = 30
    BCRYPT_ROUNDS: int = 12

    # Web / URLs
    CORS_ORIGINS: str = "http://localhost:3000"

    # Cost & safety limits
    MAX_RUN_COST_USD: float = 1.50
    MAX_TOOL_CALLS_PER_NODE: int = 8
    MAX_FACT_CHECKS_QUICK: int = 10
    MAX_FACT_CHECKS_DEEP: int = 40
    MAX_FIGURES_PER_REPORT: int = 6
    # A report where every sentence is highlighted has highlighted nothing —
    # enforced in code (synthesizer.py strips the delimiters off any
    # highlight past this count), not just left to the prompt.
    MAX_HIGHLIGHTS_PER_REPORT: int = 6
    MAX_CITATION_RETRIES: int = 2
    # Illustrations cost per-image (flat, not token-based — see NodeResult.
    # cost_override in image_generator.py) and are unverifiable by design (no
    # equivalent to chart_generator's value-grounding check exists for
    # generated pixels), so the cap is deliberately much lower than
    # MAX_FIGURES_PER_REPORT. gpt-image-1-mini at "low" quality prices at
    # ~$0.005/image — raising OPENAI_IMAGE_MODEL/IMAGE_QUALITY without also
    # updating IMAGE_COST_PER_IMAGE_USD will under-report real spend to the
    # cost ceiling.
    OPENAI_IMAGE_MODEL: str = "gpt-image-1-mini"
    IMAGE_QUALITY: str = "low"
    IMAGE_COST_PER_IMAGE_USD: float = 0.005
    MAX_ILLUSTRATIONS_PER_REPORT: int = 2
    MAX_IMAGE_BYTES: int = 5_242_880
    # How many Tavily image-search candidates web_image_fetcher tries (in
    # ranked order) before giving up on finding a real photo to pair with a
    # given illustration — most queries succeed on the first candidate; this
    # is a fallback for when it fails validation (wrong content-type, too
    # small, fails to decode).
    WEB_IMAGE_SEARCH_CANDIDATES: int = 3
    RUN_TIMEOUT_SECONDS: int = 900
    TOOL_TIMEOUT_SECONDS: int = 30
    # Trimmed dataset (5 quick-mode questions, eval/dataset/questions.jsonl)
    # is budgeted well under $2; the full 12-question set (questions_full.jsonl,
    # mixed quick/deep/academic/competitive) is not what this ceiling is sized for.
    MAX_EVAL_COST_USD: float = 1.50

    # WebSocket (Phase 3 §7.3) — no Redis Pub/Sub bridge (see app/observability/events.py's
    # module docstring for why that's safe only while the graph runs in-process).
    WS_IDLE_TIMEOUT_SECONDS: int = 60

    # Retrieval tuning
    DEDUPE_THRESHOLD: float = 0.92  # reserved for the not-yet-built dedupe node
    TOP_K_PER_SUBQUESTION: int = 8
    RRF_K: int = 60
    CONTRADICTION_NUMERIC_THRESHOLD: float = 0.15
    RERANK_CANDIDATE_LIMIT: int = 30
    # "These two evidence items are about the same underlying fact" — used by
    # fact_checker's clustering (§9) and credibility_scorer's corroboration
    # counting. Deliberately a separate constant from DEDUPE_THRESHOLD even
    # though both are cosine similarity on evidence embeddings — they serve
    # different nodes with different tolerances.
    CLAIM_SIMILARITY_THRESHOLD: float = 0.90
    # Looser than CLAIM_SIMILARITY_THRESHOLD on purpose: contradiction_detector
    # clusters numeric claims by *subject* ("battery capacity is 30.2 kWh" vs
    # "... is 45 kWh" are semantically near but not identical — they need to
    # land in the same cluster to ever get compared), not by near-duplication.
    CONTRADICTION_CLUSTER_THRESHOLD: float = 0.75

    # Reasoning effort per task tier ("none" means: don't pass reasoning_effort at all)
    EFFORT_EXTRACTION: str = "none"
    EFFORT_VERIFICATION: str = "low"
    EFFORT_PLANNING: str = "medium"
    EFFORT_SYNTHESIS: str = "medium"
    EFFORT_CONTRADICTION: str = "low"

    # Ops
    ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Per-token USD pricing, keyed by model string (PRD §13). These are estimates
# priced off PRD §3.2's stated bands for the reasoning/mini tiers, not a verified
# source (OpenAI's /v1/models endpoint doesn't expose pricing) — directionally
# correct for cost-ceiling enforcement and trace visibility, not billing-accurate.
def build_pricing(settings: Settings) -> dict[str, dict[str, float]]:
    return {
        settings.OPENAI_MODEL_REASONING: {
            "input": 2.50 / 1_000_000,
            "output": 15.00 / 1_000_000,
        },
        settings.OPENAI_MODEL_FAST: {
            "input": 0.75 / 1_000_000,
            "output": 4.50 / 1_000_000,
        },
        settings.OPENAI_EMBEDDING_MODEL: {
            "input": 0.02 / 1_000_000,
            "output": 0.0,
        },
        # Groq-hosted gpt-oss-120b — real published rate, not estimated like
        # the OpenAI entries above (Groq's pricing page is public per-model).
        settings.GROQ_MODEL_REASONING: {
            "input": 0.15 / 1_000_000,
            "output": 0.60 / 1_000_000,
        },
    }
