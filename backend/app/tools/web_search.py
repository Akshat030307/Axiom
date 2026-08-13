import asyncio
import logging

import httpx
from tavily import TavilyClient

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)
_client = TavilyClient(api_key=settings.SEARCH_API_KEY)

COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"


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


async def search_images(query: str, max_results: int = 3) -> list[dict]:
    """Tavily's own image search (include_images/include_image_descriptions)
    — genuinely relevant candidates tied to the query, already picked by
    Tavily's ranking, rather than scraping <img> tags off fetched pages
    (PRD's original image_harvester design, never built). Each result is
    {"url": ..., "description": ...}; still passed through the SSRF guard
    and content/dimension validation in figures/image_fetcher.py before
    anything is downloaded — a URL coming back from a third-party API isn't
    trusted any more than one scraped from a page."""
    response = await asyncio.to_thread(
        _client.search,
        query,
        max_results=1,
        search_depth="basic",
        include_images=True,
        include_image_descriptions=True,
        include_answer=False,
        include_raw_content=False,
        timeout=settings.TOOL_TIMEOUT_SECONDS,
    )
    return (response.get("images") or [])[:max_results]


async def search_commons_images(query: str, max_results: int = 3) -> list[dict]:
    """Wikimedia Commons search (public MediaWiki API, no key needed) for a
    real, already-existing diagram/schematic — used by image_generator to
    find an actual technical image instead of generating one. Each result is
    {"url": ..., "description": ..., "license": ...}; still passed through
    the SSRF guard and content/dimension validation in
    figures/image_fetcher.py before anything is downloaded — a URL coming
    back from a third-party API isn't trusted any more than one scraped from
    a page (same rule as search_images above)."""
    params = {
        "action": "query",
        "generator": "search",
        "gsrnamespace": "6",  # File: namespace
        "gsrsearch": query,
        "gsrlimit": str(max_results),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime",
        "iiurlwidth": "1600",
        "format": "json",
        "origin": "*",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.TOOL_TIMEOUT_SECONDS) as client:
            response = await client.get(
                COMMONS_API_URL, params=params, headers={"User-Agent": "research-agent/0.1 (+https://example.local)"}
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("search_commons_images: request failed for %r: %s", query, exc)
        return []

    pages = ((data.get("query") or {}).get("pages") or {}).values()
    results = []
    for page in pages:
        imageinfo = (page.get("imageinfo") or [None])[0]
        if not imageinfo:
            continue
        url = imageinfo.get("thumburl") or imageinfo.get("url")
        if not url:
            continue
        extmetadata = imageinfo.get("extmetadata") or {}
        license_short = (extmetadata.get("LicenseShortName") or {}).get("value")
        results.append(
            {
                "url": url,
                "description": page.get("title", "").removeprefix("File:"),
                "license": license_short,
            }
        )
    return results
