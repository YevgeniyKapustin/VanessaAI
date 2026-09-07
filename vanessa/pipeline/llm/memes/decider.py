import logging
import random

from vanessa.core.session.channel_keys import as_session_key

logger = logging.getLogger(__name__)


class MemeDecider:
    """Anti-spam gate between "a meme matches" and "we actually offer it".

    Even when a meme's keyword matches the message, it is offered only with
    ``probability`` and never more often than once per ``min_messages_between``
    bot replies in a chat. Per-chat counters live in memory; the bot is a single
    process, so this is fine (the same approach as the sticker gate).

    Usage contract with the pipeline:
    - ``register_reply(chat_id)`` on every bot reply (advances the cooldown);
    - ``register_meme(chat_id)`` when a meme block is actually injected (resets
      the cooldown to 0);
    - ``decide(chat_id)`` before injecting — ``True`` only if enabled, off
      cooldown and the probability roll passes.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        probability: float = 0.4,
        min_messages_between: int = 8,
        rng: random.Random | None = None,
    ) -> None:
        self._enabled = enabled
        self._probability = probability
        self._min_messages_between = max(1, int(min_messages_between))
        self._rng = rng or random.Random()
        self._messages_since: dict[str, int] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    def register_reply(self, chat_id: int | str) -> None:
        key = as_session_key(chat_id)
        self._messages_since[key] = self.messages_since_meme(key) + 1

    def register_meme(self, chat_id: int | str) -> None:
        self._messages_since[as_session_key(chat_id)] = 0

    def messages_since_meme(self, chat_id: int | str) -> int:
        # Start eligible so the bot's very first reply may carry a meme.
        return self._messages_since.get(
            as_session_key(chat_id),
            self._min_messages_between,
        )

    def decide(self, chat_id: int | str) -> bool:
        key = as_session_key(chat_id)
        if not self._enabled:
            logger.info("meme_skip chat_id=%s reason=disabled", key)
            return False
        if self.messages_since_meme(key) < self._min_messages_between:
            logger.info(
                "meme_skip chat_id=%s reason=cooldown messages_since=%s",
                key,
                self.messages_since_meme(key),
            )
            return False
        if self._rng.random() >= self._probability:
            logger.info(
                "meme_skip chat_id=%s reason=probability p=%.2f",
                key,
                self._probability,
            )
            return False
        return True
