import logging
import random
from collections.abc import Mapping

from services.bot.stickers.decide_predicates import (
    cooldown_blocks,
    delivery_disabled,
    probability_blocks,
)
from services.bot.stickers.decide_resolve import resolve_candidate
from services.bot.stickers.decider_pick import pick_random, pick_weighted
from services.bot.stickers.models import StickerCatalog, StickerPick

logger = logging.getLogger(__name__)


class StickerDecider:
    """Anti-spam gate between "a sticker fits" and "we actually send one".

    Even when the LLM (or the text heuristics) tagged a reply as a good fit, the
    sticker is sent only with ``probability``/``heuristic_probability`` and never
    more often than once per ``min_messages_between`` bot replies in a chat.

    Per-chat counters live in memory; the bot is a single process, so this is fine.
    """

    def __init__(
        self,
        catalog: StickerCatalog,
        *,
        enabled: bool = True,
        probability: float = 0.6,
        heuristic_probability: float = 0.45,
        min_messages_between: int = 3,
        tag_probability: Mapping[str, float] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._catalog = catalog
        self._enabled = enabled
        self._probability = probability
        self._heuristic_probability = heuristic_probability
        self._min_messages_between = max(1, int(min_messages_between))
        # Per-tag overrides of the base probability, keyed by lowercase tag.
        self._tag_probability = {
            tag.lower(): float(p) for tag, p in (tag_probability or {}).items()
        }
        self._rng = rng or random.Random()
        self._messages_since: dict[int, int] = {}

    def register_reply(self, chat_id: int) -> None:
        self._messages_since[chat_id] = self.messages_since_sticker(chat_id) + 1

    def register_sticker(self, chat_id: int) -> None:
        self._messages_since[chat_id] = 0

    def messages_since_sticker(self, chat_id: int) -> int:
        # Start eligible so the bot's very first reply may carry a sticker.
        return self._messages_since.get(chat_id, self._min_messages_between)

    def decide(
        self,
        chat_id: int,
        tag: str | None = None,
        reply_text: str | None = None,
        *,
        force: bool = False,
    ) -> StickerPick | None:
        """Decide whether to send a sticker and which one.

        ``force`` is set when the user explicitly asked for a sticker (e.g.
        «кинь стикер»): the anti-spam probability roll and the per-chat cooldown
        are then bypassed so a direct request is always honoured. If no tag was
        resolved (no LLM tag and no heuristic hit) a random sticker is sent.
        """
        if delivery_disabled(
            enabled=self._enabled,
            has_resolved_files=self._catalog.has_resolved_files,
        ):
            logger.info(
                "sticker_skip chat_id=%s tag=%r reason=disabled_or_no_files",
                chat_id,
                tag,
            )
            return None
        if self._blocked_by_cooldown(chat_id, tag, force=force):
            return None
        return self._decide_candidate(chat_id, tag, reply_text, force=force)

    def _blocked_by_cooldown(
        self, chat_id: int, tag: str | None, *, force: bool
    ) -> bool:
        messages_since = self.messages_since_sticker(chat_id)
        if not cooldown_blocks(
            force=force,
            messages_since=messages_since,
            min_messages_between=self._min_messages_between,
        ):
            return False
        logger.info(
            "sticker_skip chat_id=%s tag=%r reason=cooldown "
            "messages_since=%s",
            chat_id,
            tag,
            messages_since,
        )
        return True

    def _decide_candidate(
        self,
        chat_id: int,
        tag: str | None,
        reply_text: str | None,
        *,
        force: bool,
    ) -> StickerPick | None:
        resolved = self._resolve_candidate(tag, reply_text)
        if resolved is None:
            return self._unresolved(chat_id, tag, force=force)
        chosen_tag, from_llm = resolved
        return self._pick_if_probable(
            chat_id, tag, chosen_tag, from_llm=from_llm, force=force
        )

    def _unresolved(
        self, chat_id: int, tag: str | None, *, force: bool
    ) -> StickerPick | None:
        if force:
            return pick_random(self._catalog, self._rng, chat_id, tag)
        logger.info(
            "sticker_skip chat_id=%s tag=%r reason=no_resolvable_tag",
            chat_id,
            tag,
        )
        return None

    def _pick_if_probable(
        self,
        chat_id: int,
        tag: str | None,
        chosen_tag: str,
        *,
        from_llm: bool,
        force: bool,
    ) -> StickerPick | None:
        base = self._probability if from_llm else self._heuristic_probability
        probability = self._tag_probability.get(chosen_tag, base)
        if probability_blocks(self._rng, probability, force=force):
            logger.info(
                "sticker_skip chat_id=%s tag=%r reason=probability "
                "p=%.2f base=%.2f tag_probability=%s",
                chat_id,
                tag,
                probability,
                base,
                chosen_tag in self._tag_probability,
            )
            return None
        return pick_weighted(self._catalog, self._rng, chosen_tag)

    def _resolve_candidate(
        self,
        tag: str | None,
        reply_text: str | None,
    ) -> tuple[str, bool] | None:
        """Pick the primary tag: LLM tag wins, heuristics are the fallback."""
        return resolve_candidate(self._catalog, tag, reply_text)
