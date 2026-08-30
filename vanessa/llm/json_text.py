import re


def normalize_llm_json(raw: str) -> str:
    """Extract a JSON object from a model reply.

    Handles plain objects, ```json fenced blocks, and prose surrounding the
    object. Returns the raw text unchanged when no object can be found.
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text


__all__ = ["normalize_llm_json"]
