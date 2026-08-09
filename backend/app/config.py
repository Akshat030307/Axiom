from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Keys
    OPENAI_API_KEY: str
    SEARCH_API_KEY: str
    SEMANTIC_SCHOLAR_API_KEY: str = ""

    # Models
    OPENAI_MODEL_REASONING: str
    OPENAI_MODEL_FAST: str
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536
    SEARCH_PROVIDER: str = "tavily"

    # Infrastructure
    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"
    FIGURES_DIR: str = "/data/figures"

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
    MAX_CITATION_RETRIES: int = 2
    MAX_IMAGE_BYTES: int = 5_242_880
    RUN_TIMEOUT_SECONDS: int = 900
    TOOL_TIMEOUT_SECONDS: int = 30

    # Retrieval tuning (unused until Phase 2, kept so config shape is stable)
    DEDUPE_THRESHOLD: float = 0.92
    TOP_K_PER_SUBQUESTION: int = 8
    RRF_K: int = 60
    CONTRADICTION_NUMERIC_THRESHOLD: float = 0.15
    RERANK_CANDIDATE_LIMIT: int = 30

    # Reasoning effort per task tier ("none" means: don't pass reasoning_effort at all)
    EFFORT_EXTRACTION: str = "none"
    EFFORT_VERIFICATION: str = "low"
    EFFORT_PLANNING: str = "medium"
    EFFORT_SYNTHESIS: str = "medium"

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
    }
