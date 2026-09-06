import re


def _drop_opening_fence(lines: list[str]) -> list[str]:
    if lines and lines[0].startswith("```"):
        return lines[1:]
    return lines


def _drop_closing_fence(lines: list[str]) -> list[str]:
    if lines and lines[-1].strip() == "```":
        return lines[:-1]
    return lines


def _strip_json_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = _drop_closing_fence(_drop_opening_fence(text.splitlines()))
    return "\n".join(lines).strip()


def normalize_llm_json(raw: str) -> str:
    """Extract a JSON object from a model reply.

    Handles plain objects, ```json fenced blocks, and prose surrounding the
    object. Returns the raw text unchanged when no object can be found.
    """
    text = _strip_json_fence(raw.strip())
    if text.startswith("{") and text.endswith("}"):
        return text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0)
    return text


__all__ = ["normalize_llm_json"]
