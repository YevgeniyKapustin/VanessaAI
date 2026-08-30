from typing import ClassVar

from fastapi import Header, HTTPException, status

from vanessa.config import settings


class InternalTokenAuth:
    header: ClassVar[str] = "X-Internal-Token"

    def __init__(self, expected: str | None = None) -> None:
        self._expected = expected

    def _token(self) -> str:
        if self._expected is not None:
            return self._expected.strip()
        return settings.api_internal_token.strip()

    async def __call__(
        self,
        x_internal_token: str | None = Header(default=None),
    ) -> None:
        expected = self._token()
        if not expected:
            return
        if x_internal_token != expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid internal API token",
            )


internal_token_auth = InternalTokenAuth()
