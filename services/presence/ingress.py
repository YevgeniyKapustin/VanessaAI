from __future__ import annotations

from services.presence.models import PresenceTurn

INGRESS_ADDRESSES = frozenset({"/vanessa/input", "/chatbox/input"})


def parse_ingress_line(line: str, *, default_name: str) -> PresenceTurn | None:
    text = line.strip()
    if not text:
        return None
    name, message = split_speaker(text, default_name=default_name)
    if not message:
        return None
    return PresenceTurn(message=message, display_name=name)


def split_speaker(text: str, *, default_name: str) -> tuple[str, str]:
    for separator in (": ", "|", ":"):
        if separator not in text:
            continue
        name, rest = text.split(separator, 1)
        name, rest = name.strip(), rest.strip()
        if name and rest:
            return name, rest
    return default_name, text


def turn_from_osc(
    address: str,
    values: tuple[object, ...],
    *,
    default_name: str,
) -> PresenceTurn | None:
    if address not in INGRESS_ADDRESSES:
        return None
    strings = [str(item).strip() for item in values if isinstance(item, str)]
    strings = [item for item in strings if item]
    if not strings:
        return None
    if len(strings) == 1:
        return PresenceTurn(message=strings[0], display_name=default_name)
    return PresenceTurn(message=strings[1], display_name=strings[0])
