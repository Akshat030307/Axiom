import httpx

from app.config import get_settings
from app.guardrails.sanitize import extract_clean_text

settings = get_settings()

ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml")
MAX_FETCH_BYTES = 3_000_000


async def fetch_clean_text(url: str) -> str | None:
    """Fetch a URL and return sanitized, extracted main-content text, or None
    if the page can't be fetched or has no extractable content. Failures are
    swallowed here — the caller (web_researcher) decides how to handle a dead
    URL; one bad domain must not abort the run."""
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=settings.TOOL_TIMEOUT_SECONDS,
            headers={"User-Agent": "research-agent/0.1 (+https://example.local)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if not any(ct in content_type for ct in ALLOWED_CONTENT_TYPES):
                return None
            if len(response.content) > MAX_FETCH_BYTES:
                return None

            return extract_clean_text(response.text)
    except (httpx.HTTPError, httpx.InvalidURL):
        return None
