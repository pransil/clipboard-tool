"""NSPasteboard adapter for the general (system) clipboard."""

from __future__ import annotations

from AppKit import NSPasteboard, NSPasteboardTypeString

from ..filtering import is_sensitive
from ..watcher import Snapshot


class Pasteboard:
    def __init__(self, pasteboard=None) -> None:
        self._pb = pasteboard if pasteboard is not None else NSPasteboard.generalPasteboard()

    def change_count(self) -> int:
        return int(self._pb.changeCount())

    def snapshot(self) -> Snapshot:
        types = tuple(str(t) for t in (self._pb.types() or ()))
        if is_sensitive(types):
            # Never even read the text of a concealed/transient copy.
            return Snapshot(types, None)
        text = self._pb.stringForType_(NSPasteboardTypeString)
        return Snapshot(types, str(text) if text is not None else None)

    def write_text(self, text: str) -> int:
        """Put plain text on the clipboard. Returns the new change count."""
        self._pb.clearContents()
        self._pb.setString_forType_(text, NSPasteboardTypeString)
        return self.change_count()
