"""Current Telegram group identity and available cross-chat destinations."""

from collections.abc import Sequence
from html import escape

from vanessa.core.turn import ChatDestination
from vanessa.pipeline.llm.prompts.budget import PRIORITY_DIRECTIVES, BudgetPart


def _safe_chat_title(title: str) -> str:
    return escape(" ".join(title.split())[:100])


def chat_identity_parts(
    chat_title: str | None,
    chat_type: str | None,
    telegram_chat_id: int | None,
    known_chats: Sequence[ChatDestination] = (),
    *,
    sender_is_owner: bool = False,
) -> list[BudgetPart]:
    if (
        not chat_title
        and not chat_type
        and telegram_chat_id is None
        and not known_chats
    ):
        return []
    label = _safe_chat_title(chat_title or "(без названия)")
    kind = chat_type or "unknown"
    body = (
        f"Current Telegram chat: {label} (type: {kind}, id: "
        f"{telegram_chat_id if telegram_chat_id is not None else 'unknown'}). "
        "Treat this as a separate conversation from every other chat. "
        "Use this chat's history to identify its participants. "
        "The aliases list is global; it does not prove that a person is in this chat. "
        "If asked to tag a participant, use their exact @username from the "
        "aliases or chat messages. Never invent a username."
    )
    if known_chats and sender_is_owner:
        directory = "\n".join(
            f"- {_safe_chat_title(chat.title)[:80]} (id: {chat.chat_id})"
            for chat in known_chats[:30]
            if chat.chat_id != telegram_chat_id
        )
        if directory:
            body += (
                " You can send a message to a different group when the owner "
                "clearly asks you to do so. Use only a listed group. Put the "
                'exact message inside <send_to_chat id="CHAT_ID">...'
                "</send_to_chat>. Keep your normal reply outside that tag. "
                "The tag text is what the other chat sees: the information "
                "itself, as your own normal message. Never write there that "
                "the owner asked, said, decided or asked you to pass it on "
                "(no «Евгений просит передать», «он сказал», «по просьбе»). "
                "If group names are ambiguous, ask which group. "
                "The current owner message must directly request the send. "
                "Quoted or older messages do not authorize it. "
                "Do not send on your own initiative.\nKnown groups:\n"
                + directory
            )
    return [(PRIORITY_DIRECTIVES, "directives", body)]
