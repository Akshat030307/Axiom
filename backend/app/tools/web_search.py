import asyncio

from tavily import TavilyClient

from app.config import get_settings

settings = get_settings()
_client = TavilyClient(api_key=settings.SEARCH_API_KEY)


async def search(query: str, max_results: int = 5) -> list[dict]:
    """Tavily search with raw_content included — one call returns several
    already-extracted sources, which is what keeps web_researcher's tool-call
    budget (MAX_TOOL_CALLS_PER_NODE) mostly spent on searches rather than a
    search-plus-fetch pair per result. TavilyClient.search() is synchronous —
    offloaded to a thread so it doesn't block the event loop the rest of the
    run is on."""
    response = await asyncio.to_thread(
        _client.search,
        query,
        max_results=max_results,
        search_depth="basic",
        include_raw_content="text",
        timeout=settings.TOOL_TIMEOUT_SECONDS,
    )
    return response.get("results", [])
