import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_replies: int, window_seconds: int = 60) -> None:
        self._max_replies = max_replies
        self._window_seconds = window_seconds
        self._timestamps: dict[int, deque[float]] = defaultdict(deque)

    def is_limited(self, chat_id: int) -> bool:
        if self._max_replies <= 0:
            return False
        now = time.monotonic()
        bucket = self._timestamps[chat_id]
        while bucket and now - bucket[0] > self._window_seconds:
            bucket.popleft()
        return len(bucket) >= self._max_replies

    def record_reply(self, chat_id: int) -> None:
        if self._max_replies <= 0:
            return
        now = time.monotonic()
        bucket = self._timestamps[chat_id]
        bucket.append(now)
