import logging
import random
from typing import Mapping

from services.bot.stickers.heuristics import reply_tags
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
        if not self._enabled or not self._catalog.has_resolved_files:
            logger.info(
                "sticker_skip chat_id=%s tag=%r reason=disabled_or_no_files",
                chat_id,
                tag,
            )
            return None
        if not force and self.messages_since_sticker(chat_id) < self._min_messages_between:
            logger.info(
                "sticker_skip chat_id=%s tag=%r reason=cooldown "
                "messages_since=%s",
                chat_id,
                tag,
                self.messages_since_sticker(chat_id),
            )
            return None

        resolved = self._resolve_candidate(tag, reply_text)
        if resolved is None:
            if force:
                return self._pick_random(chat_id, tag)
            logger.info(
                "sticker_skip chat_id=%s tag=%r reason=no_resolvable_tag",
                chat_id,
                tag,
            )
            return None
        chosen_tag, from_llm = resolved

        if not force:
            base = self._probability if from_llm else self._heuristic_probability
            probability = self._tag_probability.get(chosen_tag, base)
            if self._rng.random() >= probability:
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
        return self._pick(chosen_tag)

    def _resolve_candidate(
        self,
        tag: str | None,
        reply_text: str | None,
    ) -> tuple[str, bool] | None:
        """Pick the primary tag: LLM tag wins, heuristics are the fallback."""
        if tag:
            normalized = tag.lower()
            if self._catalog.stickers_for_tag(normalized):
                return normalized, True
        for heuristic_tag in reply_tags(reply_text):
            if self._catalog.stickers_for_tag(heuristic_tag):
                return heuristic_tag, False
        return None

    def _pick(self, tag: str) -> StickerPick | None:
        candidates = self._catalog.stickers_for_tag(tag)
        if not candidates:
            return None
        weights = [max(candidate.weight, 0.0) for candidate in candidates]
        if sum(weights) <= 0:
            weights = [1.0] * len(candidates)
        chosen = self._rng.choices(candidates, weights=weights, k=1)[0]
        assert chosen.available_file_id is not None
        return StickerPick(tag=tag, file_id=chosen.available_file_id)

    def _pick_random(self, chat_id: int, tag: str | None) -> StickerPick | None:
        """Force path fallback: user asked for a sticker but no tag resolved."""
        candidates = [
            sticker
            for sticker in self._catalog.stickers
            if sticker.available_file_id
        ]
        if not candidates:
            logger.info(
                "sticker_skip chat_id=%s tag=%r reason=no_available_stickers",
                chat_id,
                tag,
            )
            return None
        chosen = self._rng.choices(candidates, k=1)[0]
        assert chosen.available_file_id is not None
        chosen_tag = chosen.tags[0] if chosen.tags else "any"
        logger.info(
            "sticker_force_random chat_id=%s requested_tag=%r chosen_tag=%s",
            chat_id,
            tag,
            chosen_tag,
        )
        return StickerPick(tag=chosen_tag, file_id=chosen.available_file_id)
