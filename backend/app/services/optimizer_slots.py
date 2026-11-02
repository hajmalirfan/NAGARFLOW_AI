"""A limit on optimizer runs at once. Each uses a CPU core for its whole time limit."""

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.config import settings

_lock = threading.Lock()
_running = 0


class OptimizerBusy(Exception):
    """Every optimizer slot is in use."""


@contextmanager
def optimizer_slot() -> Iterator[None]:
    global _running
    with _lock:
        if _running >= settings.optimizer_max_concurrent:
            raise OptimizerBusy
        _running += 1
    try:
        yield
    finally:
        with _lock:
            _running -= 1


def reset_slots() -> None:
    global _running
    with _lock:
        _running = 0
