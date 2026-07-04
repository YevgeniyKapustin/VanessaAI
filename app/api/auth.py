from fastapi import Header, HTTPException, status

from app.config import settings


async def verify_internal_token(
    x_internal_token: str | None = Header(default=None),
) -> None:
    expected = settings.api_internal_token.strip()
    if not expected:
        return
    if x_internal_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API token",
        )
