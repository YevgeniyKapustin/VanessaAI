"""Per-turn proxy flags, computed once by the gate."""

from __future__ import annotations

from dataclasses import dataclass

from vanessa.config.settings import settings
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.proxy.chat import current_proxy_chat, find_proxy_chat
from vanessa.pipeline.proxy.owner import addressed_to_owner
from vanessa.pipeline.proxy.questions import looks_like_question


@dataclass(frozen=True, slots=True)
class TurnProxyMode:
    """What this turn is: an agent's question for the owner, or the owner's DM."""

    chat_id: int | None = None
    chat_title: str | None = None
    proxy_question: bool = False
    owner_dm: bool = False

    @property
    def active(self) -> bool:
        return self.proxy_question or self.owner_dm


def is_private_chat(turn: ChatTurnInput) -> bool:
    return (turn.chat_type or "").casefold() == "private"


def detect_proxy_mode(turn: ChatTurnInput) -> TurnProxyMode:
    owner_dm = bool(
        settings.owner_dm_enabled and is_private_chat(turn) and turn.sender_is_owner
    )
    chat = current_proxy_chat(turn.chat_title, turn.telegram_chat_id)
    if chat is None and owner_dm:
        chat = find_proxy_chat(turn.known_chats)
    if chat is None:
        return TurnProxyMode(owner_dm=owner_dm)
    proxy_question = bool(
        turn.sender_is_bot
        and looks_like_question(turn.message)
        and addressed_to_owner(turn)
    )
    return TurnProxyMode(
        chat_id=chat.chat_id,
        chat_title=chat.title,
        proxy_question=proxy_question,
        owner_dm=owner_dm,
    )
