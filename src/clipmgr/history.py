"""Clipboard history logic. Pure Python, no macOS dependencies.

Two sections:
- ``recent``: the last ``cap`` (default 10) unpinned text items, newest first.
- ``pinned``: any number of items the user pinned, in pin order. They stay
  until the user unpins or deletes them, and never count toward the cap.

Every text appears at most once across both sections.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

DEFAULT_CAP = 10


@dataclass(frozen=True)
class Item:
    id: int
    text: str
    pinned: bool = False


class History:
    def __init__(self, cap: int = DEFAULT_CAP) -> None:
        if cap < 1:
            raise ValueError("cap must be at least 1")
        self.cap = cap
        self._recent: list[Item] = []
        self._pinned: list[Item] = []
        self._ids = itertools.count(1)

    # ----- views -------------------------------------------------------

    @property
    def recent(self) -> tuple[Item, ...]:
        return tuple(self._recent)

    @property
    def pinned(self) -> tuple[Item, ...]:
        return tuple(self._pinned)

    def get(self, item_id: int) -> Item | None:
        for item in itertools.chain(self._pinned, self._recent):
            if item.id == item_id:
                return item
        return None

    def __len__(self) -> int:
        return len(self._recent) + len(self._pinned)

    # ----- mutations ---------------------------------------------------

    def add(self, text: str | None) -> bool:
        """Record a newly copied text. Returns True if history changed.

        - Empty or whitespace-only text is ignored.
        - Text that matches a pinned item is ignored (it is already visible).
        - Text already in recent history moves to the top (so consecutive
          duplicates are a no-op).
        - Otherwise it is inserted at the top and the oldest items are dropped
          to keep ``cap`` recent items.
        """
        if not text or not text.strip():
            return False
        if any(item.text == text for item in self._pinned):
            return False
        for index, item in enumerate(self._recent):
            if item.text == text:
                if index == 0:
                    return False
                self._recent.insert(0, self._recent.pop(index))
                return True
        self._recent.insert(0, Item(next(self._ids), text))
        self._trim()
        return True

    def select(self, item_id: int) -> str:
        """Mark an item as chosen for pasting and return its text.

        A recent item moves to the top. A pinned item keeps its place.
        """
        index = self._index(self._recent, item_id)
        if index is not None:
            item = self._recent.pop(index)
            self._recent.insert(0, item)
            return item.text
        index = self._index(self._pinned, item_id)
        if index is not None:
            return self._pinned[index].text
        raise KeyError(item_id)

    def pin(self, item_id: int) -> None:
        index = self._index(self._recent, item_id)
        if index is None:
            if self._index(self._pinned, item_id) is not None:
                return  # already pinned
            raise KeyError(item_id)
        item = self._recent.pop(index)
        self._pinned.append(Item(item.id, item.text, pinned=True))

    def unpin(self, item_id: int) -> None:
        index = self._index(self._pinned, item_id)
        if index is None:
            if self._index(self._recent, item_id) is not None:
                return  # already unpinned
            raise KeyError(item_id)
        item = self._pinned.pop(index)
        self._recent.insert(0, Item(item.id, item.text, pinned=False))
        self._trim()

    def toggle_pin(self, item_id: int) -> None:
        if self._index(self._pinned, item_id) is not None:
            self.unpin(item_id)
        else:
            self.pin(item_id)

    def delete(self, item_id: int) -> None:
        for items in (self._recent, self._pinned):
            index = self._index(items, item_id)
            if index is not None:
                del items[index]
                return
        raise KeyError(item_id)

    def clear_history(self) -> None:
        """Remove all unpinned items. Pinned items stay."""
        self._recent.clear()

    def clear_all(self) -> None:
        """Remove everything, pinned items included."""
        self._recent.clear()
        self._pinned.clear()

    # ----- helpers -----------------------------------------------------

    def _trim(self) -> None:
        del self._recent[self.cap :]

    @staticmethod
    def _index(items: list[Item], item_id: int) -> int | None:
        for index, item in enumerate(items):
            if item.id == item_id:
                return index
        return None
