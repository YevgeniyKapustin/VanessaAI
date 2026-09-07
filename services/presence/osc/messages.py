from __future__ import annotations


def clamp01(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def avatar_param(name: str) -> str:
    return f"/avatar/parameters/{name}"


def float_param(name: str, value: float) -> tuple[str, float]:
    return avatar_param(name), clamp01(value)


def parameter_message(name: str, value: float | int) -> tuple[str, float | int]:
    return avatar_param(name), value


def chatbox_input(text: str, *, send: bool = True) -> tuple[str, str, bool]:
    return "/chatbox/input", text, send


def jaw_open(value: float, *, parameter: str = "JawOpen") -> tuple[str, float]:
    return float_param(parameter, value)


def voice_level(value: float, *, parameter: str = "Voice") -> tuple[str, float]:
    return float_param(parameter, value)
