"""HTTP JSON source shared by watches, plus the readiness probe.

A source is a base URL behind a token (the PC bridge behind the reverse SSH
tunnel today); a failed call is not an error worth a message in the chat —
the announcer simply retries on the next tick.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class JsonSource:
    """GETs one JSON object; ``payload()`` is ``{}`` whenever it fails."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        path: str,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._path = "/" + path.lstrip("/")
        self._client = client
        self._timeout = timeout_seconds

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def payload(self) -> dict:
        url = f"{self._base_url}{self._path}"
        try:
            response = await self._http.get(
                url, headers={"Authorization": f"Bearer {self._token}"}
            )
        except httpx.HTTPError as exc:
            logger.warning("announce_source_unreachable error=%s", type(exc).__name__)
            return {}
        if response.is_error:
            logger.warning("announce_source_http_error status=%s", response.status_code)
            return {}
        return _json_object(response)


def _json_object(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        logger.warning("announce_source_bad_json chars=%s", len(response.content))
        return {}
    return payload if isinstance(payload, dict) else {}


async def stand_answers(url: str, *, client: httpx.AsyncClient | None = None) -> bool:
    """Whether the public stand answers 2xx (a deploy window answers 502)."""
    if not url:
        return False
    owned = client is None
    http = client or httpx.AsyncClient(timeout=10.0)
    try:
        return await _ok(http, url)
    finally:
        if owned:
            await http.aclose()


async def _ok(http: httpx.AsyncClient, url: str) -> bool:
    try:
        response = await http.get(url, follow_redirects=True)
    except httpx.HTTPError:
        return False
    return response.is_success


__all__ = ["JsonSource", "stand_answers"]
