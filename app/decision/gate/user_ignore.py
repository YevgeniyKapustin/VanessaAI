from __future__ import annotations

import re

from app.core.messages import ContextMessage
from app.decision.gate.bot_names import text_mentions_bot_name
from app.decision.gate.ignore_registry_protocol import ChatIgnoreRegistryProtocol
from app.config.content import get_bot_name_aliases

_IGNORE_CMD = re.compile(
    r"\b(?:"
    r"игнорируй|игнорь|"
    r"не\s+отвечай|"
    r"не\s+реагируй"
    r")\b",
    re.IGNORECASE,
)

_UNIGNORE_CMD = re.compile(
    r"\b(?:"
    r"перестань\s+игнорировать|"
    r"не\s+игнорируй|"
    r"можешь\s+отвечать"
    r")\b",
    re.IGNORECASE,
)

_TARGET_PRONOUN = re.compile(
    r"\b(?:"
    r"его|ему|ним|него|"
    r"её|ее|ей|неё|нее|"
    r"этого|эту|этому"
    r")\b",
    re.IGNORECASE,
)


class ChatIgnoreRegistry:
    def __init__(self) -> None:
        self._ignored: dict[int, set[int]] = {}

    def ignore(self, chat_id: int, user_id: int) -> None:
        if user_id <= 0:
            return
        self._ignored.setdefault(chat_id, set()).add(user_id)

    def unignore(self, chat_id: int, user_id: int) -> None:
        if chat_id in self._ignored:
            self._ignored[chat_id].discard(user_id)
            if not self._ignored[chat_id]:
                del self._ignored[chat_id]

    def is_ignored(self, chat_id: int, user_id: int) -> bool:
        return user_id in self._ignored.get(chat_id, set())


def is_owner_directed_command(text: str) -> bool:
    return text_mentions_bot_name(text, get_bot_name_aliases())


def is_ignore_user_command(text: str) -> bool:
    return bool(_IGNORE_CMD.search(text.strip()))


def is_unignore_user_command(text: str) -> bool:
    return bool(_UNIGNORE_CMD.search(text.strip()))


def resolve_ignore_target(
    text: str,
    recent_messages: list[ContextMessage],
    *,
    reply_to_sender_id: int | None,
    owner_id: int,
) -> int | None:
    if reply_to_sender_id and reply_to_sender_id != owner_id:
        return reply_to_sender_id
    if not _TARGET_PRONOUN.search(text):
        return None
    for message in reversed(recent_messages):
        if message.role != "user":
            continue
        sender_id = message.sender_telegram_id
        if sender_id and sender_id != owner_id:
            return sender_id
    return None


def apply_owner_ignore_command(
    registry: ChatIgnoreRegistryProtocol,
    *,
    chat_id: int,
    owner_id: int,
    sender_id: int,
    text: str,
    recent_messages: list[ContextMessage],
    reply_to_sender_id: int | None,
) -> bool:
    if owner_id <= 0 or sender_id != owner_id:
        return False
    if not is_owner_directed_command(text):
        return False
    if is_ignore_user_command(text):
        target = resolve_ignore_target(
            text,
            recent_messages,
            reply_to_sender_id=reply_to_sender_id,
            owner_id=owner_id,
        )
        if target is None:
            return False
        registry.ignore(chat_id, target)
        return True
    if is_unignore_user_command(text):
        target = resolve_ignore_target(
            text,
            recent_messages,
            reply_to_sender_id=reply_to_sender_id,
            owner_id=owner_id,
        )
        if target is None:
            return False
        registry.unignore(chat_id, target)
        return True
    return False
