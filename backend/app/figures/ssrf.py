"""SSRF guard for downloading arbitrary web images (PRD §11.4) — required
now that source-image candidates (Tavily image search results) come from
uncontrolled URLs. Resolves and re-validates the hostname on every hop
(initial request and each redirect), rejects anything that resolves to a
private/loopback/link-local/reserved/multicast address, rejects non-http(s)
schemes, caps redirects, and enforces a byte cap while streaming rather than
trusting Content-Length.
"""

import ipaddress
import logging
import socket
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

MAX_REDIRECTS = 3


class UnsafeURLError(Exception):
    pass


def assert_safe_url(url: str) -> None:
    """Raises UnsafeURLError if `url` isn't a plain http(s) URL whose
    hostname resolves only to public, routable addresses. Called once per
    hop — a redirect can point anywhere, and a second DNS lookup can answer
    differently than the first, so this is not something to check once and
    cache across a request."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"unsupported scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise UnsafeURLError("no hostname")

    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"DNS resolution failed for {parsed.hostname!r}: {exc}") from exc

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeURLError(f"{parsed.hostname!r} resolves to a disallowed address: {ip}")


async def fetch_ssrf_safe(url: str, *, max_bytes: int, timeout: float) -> tuple[bytes, str] | None:
    """Streaming GET with per-hop SSRF revalidation and a hard byte cap
    enforced while reading. Returns (body_bytes, content_type) or None on
    any failure (unsafe URL, network error, too many redirects, over the
    byte cap) — failures are swallowed here, matching every other
    figure-producing tool in this codebase: one bad URL must not abort the
    run."""
    current = url
    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
        for _ in range(MAX_REDIRECTS + 1):
            try:
                assert_safe_url(current)
            except UnsafeURLError as exc:
                logger.info("ssrf: rejected %r: %s", current, exc)
                return None

            try:
                async with client.stream(
                    "GET", current, headers={"User-Agent": "research-agent/0.1 (+https://example.local)"}
                ) as response:
                    if 300 <= response.status_code < 400:
                        location = response.headers.get("location")
                        if not location:
                            return None
                        current = urljoin(current, location)
                        continue

                    if response.status_code != 200:
                        return None

                    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            return None
                    return bytes(body), content_type
            except httpx.HTTPError as exc:
                logger.info("ssrf: fetch failed for %r: %s", current, exc)
                return None

    logger.info("ssrf: too many redirects for %r", url)
    return None
