"""Treat SIGTERM like Ctrl+C, so `docker stop`, systemd or `kill` stop a run cleanly."""

import signal
from collections.abc import Iterator
from contextlib import contextmanager


def _interrupt(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


@contextmanager
def stop_on_sigterm() -> Iterator[None]:
    """Within this block, SIGTERM raises KeyboardInterrupt in the main thread."""
    previous = signal.signal(signal.SIGTERM, _interrupt)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)
