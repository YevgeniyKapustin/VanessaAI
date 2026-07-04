import re

_CLOSURE_PATTERNS = (
    r"\b(ладно|окей|ну\s+ладно)\b.*\b(пойду|иду|пойти|поработать|работать|спать|отойду|уйду)\b",
    r"\b(надо|пора)\b.*\b(поработать|работать|идти|пойти|уйти|спать)\b",
    r"\b(ну\s+)?(ладно|ок)\s*[,.]?\s*$",
    r"\b(пока|до\s+свидания)\b",
    r"\b(я\s+)?(пошёл|пошла|ушёл|ушла|отвалил)\b",
)
_CLOSURE_RE = re.compile("|".join(_CLOSURE_PATTERNS), re.IGNORECASE)

_DISMISSAL_PATTERNS = (
    r"\b(перестань|прекрати|заткнись|замолчи|отстань|молчи)\b",
    r"\b(не\s+)?(отвечай|пиши)\b",
    r"\bхватит\b(?!\s+ли\b)(\s*(тебе|мне))?\s*(отвечать|писать)?",
    r"^хватит[.!?]?\s*$",
    r"\bзакрой\s+(контекст|диалог)\b",
    r"\b(оставь|не\s+трогай)\s+(меня|нас)(\s+в\s+покое)?\b",
    r"\bдостаточно\b(\s*(тебе|мне))?\s*(отвечать|писать)?",
    r"\bможешь\s+молчать\b",
    r"\bотключись\b",
    r"\b(ванесса|vanessa)[,.\s]+(хватит|молчи|замолчи|отстань)\b",
    r"\b(хватит|молчи|замолчи|отстань)[,.\s]+(ванесса|vanessa)\b",
)
_DISMISSAL_RE = re.compile("|".join(_DISMISSAL_PATTERNS), re.IGNORECASE)

_GROUP_REMARK_PATTERNS = (
    r"^(видите|смотрите|видишь|смотри|ну\s+вот|вот)(\s|[,.!?]|$)",
    r"^(понял|ясно|ок\s+понял|всё\s+понял|понятно)[.!?]?\s*$",
    r"^(типа|ну|короче)\s+(да|работает|готово|запустилось)",
    r"^(ага|да|ну)\s*,?\s*(работает|готов|запустилось)",
    r"\b(работает|запустился|готов|жив[её]т|поднялся)\s*[.!?]?\s*$",
)
_GROUP_REMARK_RE = re.compile("|".join(_GROUP_REMARK_PATTERNS), re.IGNORECASE)

_THIRD_PARTY_BOT_PATTERNS = (
    r"\b(она|её|ей)\b.*\b("
    r"игнорирует|молчит|не\s+отвечает|не\s+пишет|"
    r"тупит|глючит|сломалась|не\s+работает|опять\s+молчит"
    r")\b",
    r"\b(почему|зачем|когда|что|разве)\b[^?.!]{0,40}\b(она|её)\b",
    r"\b(она|её)\b[^?.!]{0,20}\b(меня|тебя|нас)\b",
)
_THIRD_PARTY_BOT_RE = re.compile(
    "|".join(_THIRD_PARTY_BOT_PATTERNS),
    re.IGNORECASE,
)

_DIRECT_BOT_ADDRESS = re.compile(
    r"\b(ванесса|vanessa|@)\b|"
    r"\b(ты|тебя|тебе|тобой)\b",
    re.IGNORECASE,
)


def is_conversation_closure(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return True
    return bool(_CLOSURE_RE.search(normalized))


def is_dismissal_request(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    return bool(_DISMISSAL_RE.search(normalized))


def is_unsolicited_remark(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if "?" in normalized:
        return False
    return bool(_GROUP_REMARK_RE.search(normalized))


def is_third_party_about_bot(text: str) -> bool:
    normalized = text.strip()
    if not normalized or _DIRECT_BOT_ADDRESS.search(normalized):
        return False
    return bool(_THIRD_PARTY_BOT_RE.search(normalized))


def listen_window_warrants_reply(
    text: str,
    *,
    should_reply: bool | None,
    has_question: bool,
    trigger_detected: bool,
) -> bool:
    if is_unsolicited_remark(text) or is_third_party_about_bot(text):
        return False
    if should_reply is True or has_question or trigger_detected:
        return True
    if should_reply is False:
        return len(text.split()) >= 3
    return len(text.split()) >= 3


def expects_follow_up_after_bot(text: str, *, last_prior_role: str | None) -> bool:
    if last_prior_role != "assistant":
        return False
    if is_conversation_closure(text) or is_unsolicited_remark(text):
        return False
    if is_third_party_about_bot(text):
        return False
    normalized = text.strip()
    if "?" in normalized:
        return True
    return len(normalized.split()) >= 3
