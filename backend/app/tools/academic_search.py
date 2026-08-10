import httpx

from app.config import get_settings

settings = get_settings()
_WORKS_URL = "https://api.openalex.org/works"


def _reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """OpenAlex stores abstracts as a word -> [positions] inverted index
    (copyright reasons — never plain text), so this rebuilds the original
    sentence order from it. Returns None if there's no abstract at all."""
    if not inverted_index:
        return None
    positions: dict[int, str] = {}
    max_pos = 0
    for word, idxs in inverted_index.items():
        for idx in idxs:
            positions[idx] = word
            max_pos = max(max_pos, idx)
    text = " ".join(positions.get(i, "") for i in range(max_pos + 1)).strip()
    return text or None


def _best_url(work: dict) -> str | None:
    doi = work.get("doi")
    if doi:
        return doi
    landing = (work.get("primary_location") or {}).get("landing_page_url")
    if landing:
        return landing
    return work.get("id")  # OpenAlex's own work page — always present


def _strip_wildcards(query: str) -> str:
    """OpenAlex's `search` param treats `?`/`*` as wildcard operators (single-
    /multi-character match), not literal punctuation — a sub-question like
    "What causes coral bleaching?" 400s with "Invalid query parameters
    error" otherwise. Confirmed against the real API, not assumed: an
    earlier manual test happened to use a query with no "?" and looked fine
    until a real sub-question (which always ends in "?") was tried."""
    return query.replace("?", " ").replace("*", " ").strip()


async def search(query: str, max_results: int = 5) -> list[dict]:
    """OpenAlex /works search, returning the same shape as
    tools.web_search.search(): a list of {url, title, content,
    published_date}. `content` is the paper's reconstructed abstract, used
    directly as fetched_content — there's no separate page to fetch, unlike
    a web result. A work with no abstract is dropped (nothing to extract
    evidence from), same as web_researcher already drops a page with no
    extractable content."""
    params: dict[str, str | int] = {"search": _strip_wildcards(query), "per_page": max_results}
    if settings.OPENALEX_API_KEY:
        params["api_key"] = settings.OPENALEX_API_KEY

    async with httpx.AsyncClient(timeout=settings.TOOL_TIMEOUT_SECONDS) as client:
        response = await client.get(_WORKS_URL, params=params)
        response.raise_for_status()
        data = response.json()

    results: list[dict] = []
    for work in data.get("results", []):
        content = _reconstruct_abstract(work.get("abstract_inverted_index"))
        if not content:
            continue
        url = _best_url(work)
        if not url:
            continue
        year = work.get("publication_year")
        results.append(
            {
                "url": url,
                "title": work.get("title") or url,
                "content": content,
                "published_date": str(year) if year else None,
            }
        )
    return results
