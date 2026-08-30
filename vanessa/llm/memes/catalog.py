import re

from vanessa.config.content import MemeDefContent, MemesContent


def _keyword_regex(keyword: str) -> re.Pattern[str]:
    r"""Whole-token match: the keyword must appear as a standalone word.

    The ``(?<!\w)`` / ``(?!\w)`` lookarounds are Unicode-aware in Python, so a
    Cyrillic token like «ока» will NOT match inside «пока» or «оказывается» —
    only as a whole word (or whole phrase for multi-word keywords like
    «смерть в нищете»).
    """
    return re.compile(rf"(?<!\w){re.escape(keyword)}(?!\w)", re.IGNORECASE)


class MemeCatalog:
    """Curated meme catalog: keyword matching + candidate selection.

    A meme is a candidate only when one of its keywords appears as a whole token
    in the user's message. The catalog exposes the gate settings (``enabled``,
    ``probability``, ``min_messages_between``) so the pipeline and decider share
    a single source of truth from ``config/content/memes.yaml``.
    """

    def __init__(self, content: MemesContent) -> None:
        self._content = content
        self._patterns: list[tuple[MemeDefContent, list[re.Pattern[str]]]] = [
            (meme, [_keyword_regex(keyword) for keyword in meme.keywords])
            for meme in content.memes
        ]
        self._rotation = 0

    @property
    def enabled(self) -> bool:
        return self._content.enabled

    @property
    def probability(self) -> float:
        return self._content.probability

    @property
    def min_messages_between(self) -> int:
        return self._content.min_messages_between

    @property
    def max_per_reply(self) -> int:
        return self._content.max_per_reply

    @property
    def offer_on_humor(self) -> bool:
        return self._content.offer_on_humor

    @property
    def offer_max(self) -> int:
        return self._content.offer_max

    @property
    def memes(self) -> list[MemeDefContent]:
        return list(self._content.memes)

    def offerable(self, *, max_items: int | None = None) -> list[MemeDefContent]:
        """Compact proactive menu: up to ``offer_max`` memes for self-selection.

        Used when humor is appropriate but no keyword matched. A rotating window
        over the catalog keeps the menu varied across turns without repeating the
        same memes every time. Memes are returned as plain definitions; the
        prompt renders them compactly (name + usage).
        """
        limit = max_items if max_items is not None else self._content.offer_max
        memes = self.memes
        if limit <= 0 or not memes:
            return []
        count = min(limit, len(memes))
        offset = self._rotation % len(memes)
        self._rotation += count
        window = memes[offset:] + memes[:offset]
        return window[:count]

    def match(
        self,
        message: str,
        *,
        max_results: int | None = None,
    ) -> list[MemeDefContent]:
        """Return memes whose keyword appears in ``message``, in catalog order.

        Stops early at ``max_results`` (defaults to the catalog's
        ``max_per_reply``) so the prompt never overflows with meme definitions.
        """
        if not message:
            return []
        limit = max_results if max_results is not None else self._content.max_per_reply
        if limit <= 0:
            return []
        matched: list[MemeDefContent] = []
        for meme, patterns in self._patterns:
            if any(pattern.search(message) for pattern in patterns):
                matched.append(meme)
                if len(matched) >= limit:
                    break
        return matched
