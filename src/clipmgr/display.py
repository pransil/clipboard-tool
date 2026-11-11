"""Popup presentation logic: rows, key labels, previews. Pure Python.

Numbering:
- Recent items get keys 1-9 then 0 (so the 10th item is "0"). Item "1" is
  always the most recent copy.
- Pinned items get letter keys a-z, in pin order. Pins beyond 26 have no key
  and are reached with the arrow keys or a click.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .history import History, Item

RECENT_KEYS = "1234567890"
PINNED_KEYS = "abcdefghijklmnopqrstuvwxyz"

PREVIEW_LIMIT = 70
TOOLTIP_LIMIT = 500
NEWLINE_MARK = "⏎"
PIN_MARK = "📌"

_WS = re.compile(r"[ \t\f\v ]+")


@dataclass(frozen=True)
class Row:
    kind: str  # "header" | "item" | "empty"
    text: str  # header title, item preview, or empty-state message
    key: str = ""
    item: Item | None = None

    @property
    def selectable(self) -> bool:
        return self.kind == "item"


def recent_key(index: int) -> str:
    return RECENT_KEYS[index] if 0 <= index < len(RECENT_KEYS) else ""


def pinned_key(index: int) -> str:
    return PINNED_KEYS[index] if 0 <= index < len(PINNED_KEYS) else ""


def item_for_key(char: str, history: History) -> Item | None:
    """Return the item a typed character selects, or None."""
    if len(char) != 1:
        return None
    char = char.lower()
    if char in RECENT_KEYS:
        index = RECENT_KEYS.index(char)
        recent = history.recent
        return recent[index] if index < len(recent) else None
    if char in PINNED_KEYS:
        index = PINNED_KEYS.index(char)
        pinned = history.pinned
        return pinned[index] if index < len(pinned) else None
    return None


def preview(text: str, limit: int = PREVIEW_LIMIT) -> str:
    """One-line preview: whitespace collapsed, line breaks shown as ⏎."""
    lines = [_WS.sub(" ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return "(whitespace)"
    result = f" {NEWLINE_MARK} ".join(lines)
    if len(result) > limit:
        result = result[: limit - 1].rstrip() + "…"
    return result


def tooltip(text: str, limit: int = TOOLTIP_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"… ({len(text):,} characters)"


def build_rows(history: History) -> list[Row]:
    rows: list[Row] = []
    pinned, recent = history.pinned, history.recent
    if pinned:
        rows.append(Row("header", "PINNED"))
        for i, item in enumerate(pinned):
            rows.append(Row("item", f"{PIN_MARK} {preview(item.text)}", pinned_key(i), item))
        if recent:
            rows.append(Row("header", "RECENT"))
    for i, item in enumerate(recent):
        rows.append(Row("item", preview(item.text), recent_key(i), item))
    if not rows:
        rows.append(Row("empty", "Nothing copied yet"))
    return rows


def default_selection(rows: list[Row]) -> int | None:
    """Row to highlight when the popup opens: recent item 1, else the first pin."""
    for index, row in enumerate(rows):
        if row.selectable and row.item is not None and not row.item.pinned:
            return index
    return next_selectable(rows, -1, +1)


def next_selectable(rows: list[Row], start: int, step: int) -> int | None:
    """Next selectable row after ``start`` in direction ``step`` (no wrap)."""
    index = start + step
    while 0 <= index < len(rows):
        if rows[index].selectable:
            return index
        index += step
    return None


def row_for_item(rows: list[Row], item_id: int) -> int | None:
    for index, row in enumerate(rows):
        if row.item is not None and row.item.id == item_id:
            return index
    return None
