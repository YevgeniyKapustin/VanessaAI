import httpx
import logging
import time

from app.bot.messages import IncomingMessage
from app.bot.messages.response import ChatProcessResult
from app.config import settings

logger = logging.getLogger(__name__)


class HttpChatApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (base_url or settings.api_base_url).rstrip("/")
        self._timeout = timeout
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

    async def process(self, message: IncomingMessage) -> ChatProcessResult:
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
            if self._client is not None:
                response = await self._client.post(
                    url,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        url,
                        json=payload,
                        headers=headers,
                    )
                    response.raise_for_status()
                    data = response.json()
        except httpx.HTTPError as exc:
            status = (
                exc.response.status_code
                if isinstance(exc, httpx.HTTPStatusError)
                and exc.response is not None
                else None
            )
            logger.warning(
                "api_request_failed chat_id=%s status=%s duration_ms=%.1f error=%s",
                message.telegram_chat_id,
                status,
                (time.perf_counter() - started) * 1000,
                exc,
            )
            raise

        result = ChatProcessResult(
            action=str(data["action"]),
            reason=data["reason"],
            reply=data.get("reply"),
            relevance_score=float(data.get("relevance_score", 0.0)),
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
