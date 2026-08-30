from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from services.agent.deps.access import get_container
from services.agent.deps.persistence import get_turn_session
from vanessa.core.protocols import IncomingTurnHandlerProtocol


async def get_incoming_turn_handler(
    request: Request,
    session: AsyncSession = Depends(get_turn_session),
) -> IncomingTurnHandlerProtocol:
    return get_container(request).turns.handler(session)
