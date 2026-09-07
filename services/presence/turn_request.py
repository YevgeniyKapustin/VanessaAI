from __future__ import annotations

import base64
from types import UnionType
from typing import Any, Union, get_args, get_origin

from pydantic import ValidationError

from services.presence.models import PresenceTurn
from vanessa.contracts.messages import TurnImage, TurnRequest

CHANNEL = "vrchat"


def scene_image_from_jpeg(jpeg: bytes | None) -> TurnImage | None:
    if not jpeg:
        return None
    encoded = base64.b64encode(jpeg).decode("ascii")
    return TurnImage(
        data_url=f"data:image/jpeg;base64,{encoded}",
        mime_type="image/jpeg",
        telegram_file_id=None,
    )


def presence_turn_payload(turn: PresenceTurn) -> dict[str, Any]:
    message = turn.message[:4096]
    return {
        "channel": CHANNEL,
        "telegram_chat_id": None,
        "sender_telegram_id": None,
        "message": message,
        "sender_first_name": turn.display_name,
        "mentions_bot": True,
        "reply_to_bot": False,
        "reply_to_other_user": False,
        "images": [],
        "scene_image": scene_image_from_jpeg(turn.scene_jpeg),
        "chat_title": None,
        "chat_type": None,
    }


def _is_optional_int(annotation: object) -> bool:
    origin = get_origin(annotation)
    if origin is Union or origin is UnionType:
        args = get_args(annotation)
        return int in args and type(None) in args
    return False


def vrchat_contract_ready() -> bool:
    fields = TurnRequest.model_fields
    if "channel" not in fields or "scene_image" not in fields:
        return False
    chat = fields.get("telegram_chat_id")
    sender = fields.get("sender_telegram_id")
    if chat is None or sender is None:
        return False
    return _is_optional_int(chat.annotation) and _is_optional_int(sender.annotation)


def build_turn_request(
    turn: PresenceTurn,
    *,
    correlation_id: str,
    reply_to: str,
) -> TurnRequest:
    payload = presence_turn_payload(turn)
    payload["correlation_id"] = correlation_id
    payload["reply_to"] = reply_to
    return TurnRequest(**payload)


def try_build_turn_request(
    turn: PresenceTurn,
    *,
    correlation_id: str,
    reply_to: str,
) -> TurnRequest | None:
    if not vrchat_contract_ready():
        return None
    try:
        return build_turn_request(
            turn,
            correlation_id=correlation_id,
            reply_to=reply_to,
        )
    except (TypeError, ValidationError):
        return None
