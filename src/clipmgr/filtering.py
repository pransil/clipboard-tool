"""Decide whether a clipboard change should be recorded. Pure Python.

Password managers mark sensitive copies with the nspasteboard.org marker
types. Any copy carrying one of them is never stored.
See http://nspasteboard.org/
"""

from __future__ import annotations

from collections.abc import Iterable

CONCEALED_TYPE = "org.nspasteboard.ConcealedType"
TRANSIENT_TYPE = "org.nspasteboard.TransientType"

SKIP_TYPES = frozenset({CONCEALED_TYPE, TRANSIENT_TYPE})


def is_sensitive(types: Iterable[str] | None) -> bool:
    return any(str(t) in SKIP_TYPES for t in (types or ()))


def should_record(types: Iterable[str] | None, text: str | None) -> bool:
    """True if a pasteboard snapshot is plain text that may be stored."""
    if is_sensitive(types):
        return False
    return bool(text and text.strip())
