from sqlalchemy.ext.asyncio import AsyncSession

from services.agent.deps.access import get_container
from vanessa.core.protocols import IncomingTurnHandlerProtocol


async def get_incoming_turn_handler(
    request,
    session: AsyncSession,
) -> IncomingTurnHandlerProtocol:
    return get_container(request).turns.handler(session)
