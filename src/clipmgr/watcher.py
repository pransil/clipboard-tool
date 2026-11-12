"""Clipboard polling logic. Pure Python; the pasteboard is injected.

macOS has no clipboard-change event, so the app calls ``poll()`` several
times per second. Each call compares the pasteboard's change count with the
last one seen and only reads the contents when it has changed.

Normally a new copy goes to History (unless it is marked sensitive). While
``capture`` is set (the login helper is collecting a username and password),
every copy goes to that callback instead, sensitive or not, and never to
History.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .filtering import should_record
from .history import History


@dataclass(frozen=True)
class Snapshot:
    types: tuple[str, ...]
    text: str | None


class ClipboardWatcher:
    def __init__(
        self,
        read_change_count: Callable[[], int],
        read_snapshot: Callable[[bool], Snapshot],
        history: History,
    ) -> None:
        """``read_snapshot(include_sensitive)`` must leave ``text`` as None for a
        concealed/transient copy unless ``include_sensitive`` is True."""
        self._read_change_count = read_change_count
        self._read_snapshot = read_snapshot
        self._history = history
        self._last_count: int | None = None
        self._ignored: set[int] = set()
        self.capture: Callable[[str], None] | None = None

    def ignore(self, change_count: int) -> None:
        """Skip the given change count (used for the app's own writes)."""
        self._ignored.add(change_count)

    def poll(self) -> bool:
        """Check the pasteboard once. Returns True if history changed."""
        count = self._read_change_count()
        if count == self._last_count:
            return False
        self._last_count = count
        if count in self._ignored:
            self._ignored.discard(count)
            return False
        # Older ignored counts can never match again; drop them.
        self._ignored = {c for c in self._ignored if c > count}
        if self.capture is not None:
            snapshot = self._read_snapshot(True)
            if snapshot.text:
                self.capture(snapshot.text)
            return False
        snapshot = self._read_snapshot(False)
        if not should_record(snapshot.types, snapshot.text):
            return False
        return self._history.add(snapshot.text)
