"""Download + validate a candidate source image (PRD §11.2 rules, applied to
Tavily image-search results rather than scraped <img> tags — see
graph/nodes/web_image_fetcher.py). Every failure mode is swallowed and
returns None: a single bad candidate must not abort the run, just try the
next one.
"""

import io
import logging

from PIL import Image, UnidentifiedImageError

from app.config import get_settings
from app.figures.ssrf import fetch_ssrf_safe

settings = get_settings()
logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
MIN_DIMENSION_PX = 200
MAX_DIMENSION_PX = 4000


async def fetch_and_validate_image(url: str) -> tuple[bytes, str, str] | None:
    """Returns (bytes, content_type, extension) for a URL that resolves to a
    safe host, serves an allowed image content-type, is under
    MAX_IMAGE_BYTES, decodes cleanly, and falls within the 200-4000px bound
    on both dimensions — or None if any check fails."""
    result = await fetch_ssrf_safe(url, max_bytes=settings.MAX_IMAGE_BYTES, timeout=settings.TOOL_TIMEOUT_SECONDS)
    if result is None:
        return None
    data, content_type = result

    ext = ALLOWED_CONTENT_TYPES.get(content_type)
    if ext is None:
        logger.info("image_fetcher: rejected %r, disallowed content-type %r", url, content_type)
        return None

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()  # forces full decode, raising on truncated/corrupt data
            width, height = img.size
    except (UnidentifiedImageError, OSError) as exc:
        logger.info("image_fetcher: rejected %r, failed to decode: %s", url, exc)
        return None

    if not (MIN_DIMENSION_PX <= width <= MAX_DIMENSION_PX and MIN_DIMENSION_PX <= height <= MAX_DIMENSION_PX):
        logger.info("image_fetcher: rejected %r, out-of-bounds dimensions %dx%d", url, width, height)
        return None

    return data, content_type, ext
