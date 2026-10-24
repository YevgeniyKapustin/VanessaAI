"""Display label for messages written by other Telegram bots (AI peers).

A bot sender gets no user row and no person card. Its messages keep this
label in ``messages.sender_display_name`` so prompts show «[бот Имя]» and
memory/metrics jobs can skip them.
"""

BOT_LABEL_PREFIX = "[бот "
_BOT_LABEL_SUFFIX = "]"
_UNNAMED_BOT = "без имени"


def is_bot_sender_label(name: str | None) -> bool:
    if not name:
        return False
    return name.startswith(BOT_LABEL_PREFIX) and name.endswith(_BOT_LABEL_SUFFIX)


def bot_sender_label(name: str | None) -> str:
    if is_bot_sender_label(name):
        return str(name)
    clean = (name or "").strip().lstrip("@") or _UNNAMED_BOT
    return f"{BOT_LABEL_PREFIX}{clean}{_BOT_LABEL_SUFFIX}"
