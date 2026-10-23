"""Owner Telegram accounts: the required user plus extra accounts of the same person."""

from __future__ import annotations

from vanessa.config.settings import settings


def owner_telegram_ids() -> frozenset[int]:
    """All owner account ids; empty when no owner is configured."""
    ids = {settings.required_user_telegram_id}
    for raw in settings.owner_extra_telegram_ids.split(","):
        part = raw.strip()
        if part.lstrip("-").isdigit():
            ids.add(int(part))
    ids.discard(0)
    return frozenset(ids)


def is_owner(telegram_id: int | None) -> bool:
    return bool(telegram_id) and telegram_id in owner_telegram_ids()


def owner_id_for(sender_telegram_id: int | None) -> int:
    """The sender's own id when the sender is an owner, else the primary owner id."""
    if is_owner(sender_telegram_id):
        return int(sender_telegram_id or 0)
    return settings.required_user_telegram_id
