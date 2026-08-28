import json
import logging
import time
from collections.abc import Awaitable, Callable

import httpx

from app.bot.messages import IncomingMessage
from app.bot.messages.response import ChatProcessResult
from app.config import settings
from app.observability.metrics import record_http_client

logger = logging.getLogger(__name__)


class HttpChatApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        connect_timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (base_url or settings.api_base_url).rstrip("/")
        # The pipeline (Gate -> Retrieve -> Compose -> Critique) can take 2-6s+,
        # so the read/write timeout must be generous; the connect timeout stays
        # short so an unreachable API fails fast instead of hanging the handler.
        self._timeout = (
            timeout if timeout is not None else settings.api_client_read_timeout
        )
        self._connect_timeout = (
            connect_timeout
            if connect_timeout is not None
            else settings.api_client_connect_timeout
        )
        self._timeout_config = httpx.Timeout(
            read=self._timeout,
            write=self._timeout,
            connect=self._connect_timeout,
            pool=self._connect_timeout,
        )
        self._client = client

    def _request_headers(self, message: IncomingMessage) -> dict[str, str]:
        headers = {
            "X-Request-ID": (
                f"{message.telegram_chat_id}:{message.telegram_message_id}"
            ),
        }
        token = settings.api_internal_token.strip()
        if token:
            headers["X-Internal-Token"] = token
        return headers

    async def process(
        self,
        message: IncomingMessage,
        on_started: Callable[[], Awaitable[None]] | None = None,
    ) -> ChatProcessResult:
        url = f"{self._base_url}/api/v1/chat"
        payload = message.to_api_payload()
        headers = self._request_headers(message)
        started = time.perf_counter()
        logger.info(
            "api_request_start chat_id=%s message_id=%s",
            message.telegram_chat_id,
            message.telegram_message_id,
        )
        try:
            data, status_code = await self._post(url, payload, headers, on_started)
        except httpx.HTTPError as exc:
            status = (
                exc.response.status_code
                if isinstance(exc, httpx.HTTPStatusError)
                and exc.response is not None
                else None
            )
            record_http_client(
                service="api",
                status=status,
                seconds=time.perf_counter() - started,
            )
            logger.warning(
                "api_request_failed chat_id=%s status=%s duration_ms=%.1f error=%s",
                message.telegram_chat_id,
                status,
                (time.perf_counter() - started) * 1000,
                exc,
            )
            raise

        messages = data.get("messages")
        result = ChatProcessResult(
            action=str(data["action"]),
            reason=data["reason"],
            reply=data.get("reply"),
            messages=(
                [str(part) for part in messages]
                if isinstance(messages, list)
                else None
            ),
            relevance_score=float(data.get("relevance_score", 0.0)),
            sticker_tag=data.get("sticker_tag"),
            photo_file_id=data.get("photo_file_id"),
            photo_data_url=data.get("photo_data_url"),
        )
        record_http_client(
            service="api",
            status=status_code,
            seconds=time.perf_counter() - started,
        )
        logger.info(
            "api_request_done chat_id=%s action=%s reason=%s "
            "relevance=%.3f duration_ms=%.1f",
            message.telegram_chat_id,
            result.action,
            result.reason,
            result.relevance_score,
            (time.perf_counter() - started) * 1000,
        )
        return result

    async def _post(
        self,
        url: str,
        payload: dict,
        headers: dict[str, str],
        on_started: Callable[[], Awaitable[None]] | None,
    ) -> tuple[dict, int]:
        if self._client is not None:
            async with self._client.stream(
                "POST", url, json=payload, headers=headers
            ) as response:
                response.raise_for_status()
                data = await self._read_body(response, on_started)
                return data, response.status_code
        async with httpx.AsyncClient(timeout=self._timeout_config) as client:
            async with client.stream(
                "POST", url, json=payload, headers=headers
            ) as response:
                response.raise_for_status()
                data = await self._read_body(response, on_started)
                return data, response.status_code

    async def _read_body(
        self,
        response: httpx.Response,
        on_started: Callable[[], Awaitable[None]] | None,
    ) -> dict:
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return await self._parse_sse(response, on_started)
        # Plain-JSON fallback (older API / non-streaming path).
        return response.json()

    async def _parse_sse(
        self,
        response: httpx.Response,
        on_started: Callable[[], Awaitable[None]] | None,
    ) -> dict:
        """Consume an SSE stream and return the final `result` payload.

        A `started` event means the decision gate passed and the pipeline is
        composing an actual answer — at that point `on_started` is fired so the
        bot can show the "typing..." indicator for the rest of the turn.
        """
        event_name: str | None = None
        data_lines: list[str] = []
        async for line in response.aiter_lines():
            if line == "":
                if event_name == "started":
                    if on_started is not None:
                        try:
                            await on_started()
                        except Exception:
                            logger.warning(
                                "on_started_callback_failed",
                                exc_info=True,
                            )
                elif event_name == "result":
                    return json.loads("\n".join(data_lines))
                event_name = None
                data_lines = []
            elif line.startswith("event:"):
                event_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        if event_name == "result":
            return json.loads("\n".join(data_lines))
        raise httpx.ProtocolError("SSE stream ended without a result event")
