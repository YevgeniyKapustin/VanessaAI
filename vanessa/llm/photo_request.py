"""Explicit photo-send request detection.

A deterministic regex fallback (mirroring the sticker request heuristic in
``services.bot.stickers.heuristics``) that answers "did the user explicitly ask the
bot to send / show / return a photo?". Used in two places:

- the prompt builder, to require the ``[photo:<index>]`` marker when the album is
  non-empty or to force an honest refusal when the album is empty;
- the pipeline (ComposeStage), to flag photo requests that resolved to no actual
  delivery (the "сказала что отправила, но фото не пришло" bug).

The regex is intentionally a safety net: the hard honesty rule lives in the
compose prompt itself (``photo_album_instruction`` / ``photo_album_empty_note``)
and applies even when this heuristic misses.
"""

import re

# Photo words — Russian (фото, картинка, фотка, фотография, скрин, пикча) and
# English (photo, picture, image, pic). ``\w*`` lets a prefix cover declined
# forms («картинку», «картинки»); ``pic\b`` is bounded because "pic" is a short
# English stem.
_PHOTO_WORDS = (
    r"фото\w*|фотк\w*|картинк\w*|скрин\w*|скриншот\w*|пикч\w*"
    r"|photo\w*|picture\w*|image\w*|pic\b"
)

# Send / show / return verbs — the same family as the sticker heuristic, plus
# plural/formal imperative forms («отправьте», «скиньте», «дайте») so a direct
# request is not missed.
_SEND_VERBS = (
    r"кинь|киньте|скинь|скиньте|дай|дайте|сбрось|сбросьте|пришли|пришлите"
    r"|покажи|покажите|кидай|брось|дропни|показывай"
    r"|отправь|отправьте|отправить|отправляй|шли|шлёшь|шлите"
    r"|верни|верните|вернуть"
)

# Optional filler between the verb and the photo word: «мне», «любую»,
# «какую-нибудь / какую угодно», polite particles («плиз/пожалуйста») and
# demonstratives («то/ту/эту/вон»), so «отправь любую картинку»,
# «верни то фото» and «кинь плиз картинку» all match.
_MID = (
    r"(?:(?:мне|любую|какую[- ]нибудь|какую\s+угодно|нормальную"
    r"|плиз|пожалуйста|то|ту|эту|этот|эти|вон)\s+)*"
)

# An explicit "any" request where the photo noun is left implicit
# («пришли любую» / «любую отправить» — the reported «просил любую отправить»).
# NOTE: always wrap in (?:...) when interpolating — a bare alternation would
# make «\bлюбую» a standalone alternative (matching "любую" anywhere).
_ANY = r"любую|какую[- ]нибудь|какую\s+угодно"

_EN_VERBS = r"send|show|return|give"

_PHOTO_REQUEST = re.compile(
    rf"(?:{_SEND_VERBS})\s+{_MID}(?:{_PHOTO_WORDS})"
    rf"|\b(?:{_PHOTO_WORDS})\s+(?:мне\s+)*(?:{_SEND_VERBS})"
    rf"|\b(?:{_ANY})\s+(?:{_SEND_VERBS})"
    rf"|(?:{_SEND_VERBS})\s+(?:{_ANY})\s*$"
    rf"|(?:{_EN_VERBS})\s+(?:me\s+)?(?:the\s+|a\s+|an\s+)?"
    rf"(?:photo|picture|image|pic)\b"
    rf"|\b(?:photo|picture|image|pic)\b\s*!",
    re.IGNORECASE,
)


def is_photo_request(text: str | None) -> bool:
    """True when the user explicitly asked the bot to send / show a photo."""
    if not text:
        return False
    return bool(_PHOTO_REQUEST.search(text))
