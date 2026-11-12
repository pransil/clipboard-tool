"""NSPasteboard adapter for the general (system) clipboard."""

from __future__ import annotations

from AppKit import (
    NSPasteboard,
    NSPasteboardContentsCurrentHostOnly,
    NSPasteboardItem,
    NSPasteboardTypeString,
)
from Foundation import NSData

from ..filtering import CONCEALED_TYPE, TRANSIENT_TYPE, is_sensitive
from ..watcher import Snapshot

# A saved clipboard: one {type: data} dict per pasteboard item.
SavedClipboard = list[dict[str, NSData]]


class Pasteboard:
    def __init__(self, pasteboard=None) -> None:
        self._pb = pasteboard if pasteboard is not None else NSPasteboard.generalPasteboard()

    def change_count(self) -> int:
        return int(self._pb.changeCount())

    def snapshot(self, include_sensitive: bool = False) -> Snapshot:
        types = tuple(str(t) for t in (self._pb.types() or ()))
        if is_sensitive(types) and not include_sensitive:
            # Never even read the text of a concealed/transient copy, except
            # when the login helper is explicitly capturing one.
            return Snapshot(types, None)
        text = self._pb.stringForType_(NSPasteboardTypeString)
        return Snapshot(types, str(text) if text is not None else None)

    def write_text(self, text: str) -> int:
        """Put plain text on the clipboard. Returns the new change count."""
        self._pb.clearContents()
        self._pb.setString_forType_(text, NSPasteboardTypeString)
        return self.change_count()

    def write_secret(self, text: str) -> int:
        """Put a login value on the clipboard for one paste.

        Marked concealed + transient so clipboard managers skip it, and kept to
        this Mac so Universal Clipboard doesn't send it to other devices.
        """
        self._pb.prepareForNewContentsWithOptions_(NSPasteboardContentsCurrentHostOnly)
        item = NSPasteboardItem.alloc().init()
        item.setString_forType_(text, NSPasteboardTypeString)
        for marker in (CONCEALED_TYPE, TRANSIENT_TYPE):
            item.setData_forType_(NSData.data(), marker)
        self._pb.writeObjects_([item])
        return self.change_count()

    def save(self) -> SavedClipboard:
        """Copy everything on the clipboard (all items, all types) into memory."""
        saved: SavedClipboard = []
        for item in self._pb.pasteboardItems() or ():
            entry = {}
            for kind in item.types() or ():
                data = item.dataForType_(kind)
                if data is not None:
                    entry[str(kind)] = data
            if entry:
                saved.append(entry)
        return saved

    def restore(self, saved: SavedClipboard) -> int:
        """Put back a clipboard from ``save()``. Returns the new change count."""
        self._pb.clearContents()
        items = []
        for entry in saved:
            item = NSPasteboardItem.alloc().init()
            for kind, data in entry.items():
                item.setData_forType_(data, kind)
            items.append(item)
        if items:
            self._pb.writeObjects_(items)
        return self.change_count()
