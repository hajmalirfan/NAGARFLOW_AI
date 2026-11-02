"""Rate limits held in memory.

Counts are per process and vanish on restart. The security report records
that as a known limit.
"""

import threading
import time
from collections import deque
from collections.abc import Callable

LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_S = 15 * 60
FORGOT_PASSWORD_ATTEMPTS = 5
FORGOT_PASSWORD_WINDOW_S = 60 * 60
SWEEP_AT_KEYS = 10_000


class RateLimiter:
    def __init__(
        self, limit: int, window_s: float, clock: Callable[[], float] = time.monotonic,
        sweep_at: int = SWEEP_AT_KEYS,
    ) -> None:
        self.limit = limit
        self.window_s = window_s
        self.clock = clock
        self.sweep_at = sweep_at
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}

    def _prune(self, key: str, now: float) -> None:
        hits = self._hits.get(key)
        if hits is None:
            return
        while hits and now - hits[0] >= self.window_s:
            hits.popleft()
        if not hits:
            del self._hits[key]

    def is_blocked(self, key: str) -> bool:
        return self.count(key) >= self.limit

    def count(self, key: str) -> int:
        with self._lock:
            self._prune(key, self.clock())
            return len(self._hits.get(key, ()))

    def record(self, key: str) -> None:
        with self._lock:
            now = self.clock()
            # Addresses and emails come from anyone, so the store must not
            # grow without limit.
            if len(self._hits) >= self.sweep_at:
                for stored in list(self._hits):
                    self._prune(stored, now)
            self._hits.setdefault(key, deque()).append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def size(self) -> int:
        with self._lock:
            return len(self._hits)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_limiter = RateLimiter(LOGIN_ATTEMPTS, LOGIN_WINDOW_S)
forgot_password_limiter = RateLimiter(FORGOT_PASSWORD_ATTEMPTS, FORGOT_PASSWORD_WINDOW_S)
