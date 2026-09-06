from sqlalchemy.ext.asyncio import AsyncSession

from vanessa.core.protocols import UserRepositoryProtocol
from vanessa.infrastructure.db.repository import MessageRepository, UserRepository
from vanessa.infrastructure.db.uow import SqlAlchemyUnitOfWork


class Persistence:
    def unit_of_work(self, session: AsyncSession) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session)

    def messages(self, session: AsyncSession) -> MessageRepository:
        return MessageRepository(session)

    def users(self, session: AsyncSession) -> UserRepositoryProtocol:
        return UserRepository(session)
