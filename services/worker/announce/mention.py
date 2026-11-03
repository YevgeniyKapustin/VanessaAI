"""Find the chat participant behind an event actor, for a real @-mention.

Source names are not Telegram handles (Leonid Lichkun is @Canoist in the
chat), and a bot's HTML message does not auto-link a bare ``@name`` — only
an explicit link notifies. The lookup is name-based against Vanessa's own
user directory: every token of the source name must appear in the person's
name, username or nickname; a one-word name needs an exact username match.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import select

from vanessa.infrastructure.db.models import User

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Participant:
    """A person Vanessa can mention in a chat."""

    telegram_id: int
    username: str
    name: str

    @property
    def label(self) -> str:
        return f"@{self.username}" if self.username else self.name

    @property
    def markdown(self) -> str:
        """A Telegram mention link: HTML anchors never come from plain text."""
        return f"[{self.label}](tg://user?id={self.telegram_id})"


def _tokens(text: str | None) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    return {
        token
        for token in re.split(r"[^0-9a-zа-яё]+", normalized)
        if len(token) > 1
    }


def _person_text(user: User) -> str:
    return " ".join(
        part
        for part in (user.first_name, user.last_name, user.username, user.nickname)
        if part
    )


def _as_participant(user: User) -> Participant:
    name = " ".join(part for part in (user.first_name, user.last_name) if part)
    return Participant(
        telegram_id=int(user.telegram_id),
        username=(user.username or "").strip(),
        name=name or (user.username or "участник"),
    )


def _match(user: User, wanted: set[str]) -> Participant | None:
    if len(wanted) == 1:
        username = (user.username or "").casefold()
        return _as_participant(user) if username and username in wanted else None
    return _as_participant(user) if wanted <= _tokens(_person_text(user)) else None


async def find_mention(session_factory, name: str) -> Participant | None:
    """The most specific participant whose name covers every token of ``name``."""
    wanted = _tokens(name)
    if not wanted:
        return None
    users = await _load_users(session_factory)
    return None if users is None else _best_match(users, wanted)


async def _load_users(session_factory) -> list[User] | None:
    try:
        async with session_factory() as session:
            return (await session.execute(select(User))).scalars().all()
    except Exception:
        logger.exception("announce_mention_lookup_failed")
        return None


def _best_match(users: list[User], wanted: set[str]) -> Participant | None:
    best: tuple[int, Participant] | None = None
    for user in users:
        participant = _match(user, wanted)
        if participant is None:
            continue
        extra = len(_tokens(_person_text(user)) - wanted)
        if best is None or extra < best[0]:
            best = (extra, participant)
    return best[1] if best else None


__all__ = ["Participant", "find_mention"]
