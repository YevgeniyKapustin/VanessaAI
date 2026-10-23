"""HTTP client for the Hermes Agent API server (``/health`` + ``/v1/runs``).

Hermes runs on the owner's PC and is reached through a reverse SSH tunnel.
Runs are asynchronous: start one, then poll it, so a dropped tunnel never
kills a long Hermes task. Streaming is not used (its error chunks are not
redacted upstream).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from vanessa.infrastructure.hermes.models import HermesRun, HermesUnavailableError

logger = logging.getLogger(__name__)


class HermesClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client
        self._timeout = timeout_seconds

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        headers.update(extra or {})
        return headers

    async def is_online(self) -> bool:
        try:
            response = await self._http.get(f"{self._base_url}/health")
        except httpx.HTTPError:
            return False
        return response.is_success

    async def start_run(
        self,
        question: str,
        *,
        session_id: str,
        idempotency_key: str,
        instructions: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {"input": question, "session_id": session_id}
        if instructions:
            payload["instructions"] = instructions
        data = await self._request(
            "POST",
            "/v1/runs",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
        )
        run_id = str(data.get("run_id") or "")
        if not run_id:
            raise HermesUnavailableError("hermes returned no run_id")
        return run_id

    async def get_run(self, run_id: str) -> HermesRun:
        data = await self._request("GET", f"/v1/runs/{run_id}")
        return HermesRun(
            run_id=run_id,
            status=str(data.get("status") or "unknown"),
            output=str(data.get("output") or "").strip(),
        )

    async def stop_run(self, run_id: str) -> None:
        await self._request("POST", f"/v1/runs/{run_id}/stop")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._http.request(
                method,
                f"{self._base_url}{path}",
                json=json,
                headers=self._headers(headers),
            )
        except httpx.HTTPError as exc:
            raise HermesUnavailableError(f"hermes unreachable: {exc}") from exc
        if response.is_error:
            # Body may echo provider errors; log only the status.
            logger.warning(
                "hermes_http_error path=%s status=%s", path, response.status_code
            )
            raise HermesUnavailableError(f"hermes http {response.status_code}")
        return response.json() if response.content else {}
