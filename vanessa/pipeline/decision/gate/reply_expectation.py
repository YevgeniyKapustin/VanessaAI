import re

from vanessa.core.messages import ContextMessage

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
    r"\bзакрой\s+(контекст|диалог|сессию)\b",
    (
        r"\b(уйди|уходи|убирайся|сгинь|сгиньте|исчезни|исчезай|"
        r"свали|отвали|отстань)\b"
    ),
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
    (
        r"\b(она|её|ей)\b.*\b("
        r"игнорирует|молчит|не\s+отвечает|не\s+пишет|"
        r"тупит|глючит|сломалась|не\s+работает|опять\s+молчит"
        r")\b"
    ),
    r"\b(почему|зачем|когда|что|разве)\b[^?.!]{0,40}\b(она|её)\b",
    r"\b(она|её)\b[^?.!]{0,20}\b(меня|тебя|нас)\b",
    (
        r"\bона\b[^.!]{0,80}\b("
        r"понимает|не\s+понимает|плохо\s+понимает|"
        r"не\s+всегда\s+понимает|думает|ошибается|теряет"
        r")\b"
    ),
    r"\b(ей|её)\b[^.!]{0,40}\b(отвечают|писали|обращаются)\b",
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

_IMPERATIVE_START = re.compile(
    r"^(?:"
    r"продолжай|продолжи|дальше|ещё|еще|"
    r"напиши|скажи|давай|добавь|перечисли|"
    r"повтори|ответь|расскажи|слушай|"
    r"ну\s+(?:давай|продолжай|дальше)"
    r")\b",
    re.IGNORECASE,
)

_VOCATIVE_COMMA = re.compile(
    r"^[a-zа-яё]{2,}\s*,",
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
    if not normalized:
        return False
    if re.search(r"\b(ванесса|vanessa)\b", normalized, re.IGNORECASE):
        return False
    return bool(_THIRD_PARTY_BOT_RE.search(normalized))


def is_contextual_vocative_address(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if is_unsolicited_remark(normalized):
        return False
    if is_third_party_about_bot(normalized):
        return False
    if _IMPERATIVE_START.search(normalized):
        return True
    return bool(_VOCATIVE_COMMA.search(normalized))


def mention_warrants_reply(
    text: str,
    *,
    should_reply: bool | None = None,
    reply_to_bot: bool = False,
) -> bool:
    """Whether a message that mentions the bot implies the sender expects a reply.

    A direct mention (name/alias/mention entity) normally warrants a reply.
    It does not when the message is clearly not directed at the bot: a status
    remark, an unsolicited group observation, third-party talk about the bot,
    or a conversation closer. A direct reply to the bot or an explicit planner
    go-ahead always warrants a reply.
    """
    if reply_to_bot:
        return True
    if should_reply is True:
        return True
    if is_conversation_closure(text):
        return False
    if is_unsolicited_remark(text):
        return False
    return not is_third_party_about_bot(text)


_BOT_PRONOUN_REPLY = re.compile(
    r"^я\s+(её|ей)\b|"
    r"\b(она|её)\b[^.!]{0,30}\b("
    r"уважаю|люблю|обожаю|крутая|классная|норм|молодец|"
    r"согласен|согласна"
    r")\b",
    re.IGNORECASE,
)


def is_bot_pronoun_reply(text: str) -> bool:
    normalized = text.strip()
    if not normalized or is_third_party_about_bot(normalized):
        return False
    return bool(_BOT_PRONOUN_REPLY.search(normalized))


def last_prior_role(messages: list[ContextMessage]) -> str | None:
    if len(messages) < 2:
        return None
    return messages[-2].role


def listen_window_warrants_reply(
    text: str,
    *,
    should_reply: bool | None,
    has_question: bool,
    trigger_detected: bool,
) -> bool:
    if is_unsolicited_remark(text) or is_third_party_about_bot(text):
        return False
    if should_reply is False:
        # The LLM planner explicitly vetoed a reply — honor it.
        return False
    if should_reply is True or trigger_detected or has_question:
        return True
    if is_bot_pronoun_reply(text):
        return True
    if is_contextual_vocative_address(text):
        return True
    # Inside the post-reply window a substantive message that continues the
    # thread (not noise/closure/unsolicited/third-party) is a candidate: the
    # bot participates in the dialogue unless the planner vetoed a reply.
    return True


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
