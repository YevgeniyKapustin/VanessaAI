import re

_CLOSURE_PATTERNS = (
    r"\b(ладно|окей|ну\s+ладно)\b.*\b(пойду|иду|пойти|поработать|работать|спать|отойду|уйду)\b",
    r"\b(надо|пора)\b.*\b(поработать|работать|идти|пойти|уйти|спать)\b",
    r"\b(ну\s+)?(ладно|ок)\s*[,.]?\s*$",
    r"\b(пока|до\s+свидания)\b",
    r"\b(я\s+)?(пошёл|пошла|ушёл|ушла|отвалил)\b",
)
_CLOSURE_RE = re.compile("|".join(_CLOSURE_PATTERNS), re.IGNORECASE)


def is_conversation_closure(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return True
    return bool(_CLOSURE_RE.search(normalized))


def expects_follow_up_after_bot(text: str, *, last_prior_role: str | None) -> bool:
    if last_prior_role != "assistant":
        return False
    if is_conversation_closure(text):
        return False
    return True
