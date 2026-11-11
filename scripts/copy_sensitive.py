"""Manual test helper: copy text marked the way password managers mark secrets.

    uv run python scripts/copy_sensitive.py              # ConcealedType
    uv run python scripts/copy_sensitive.py --transient  # TransientType

clipmgr must NOT show this text in its popup. (It does land on the real
clipboard, so ⌘V will still paste it, exactly as with a password manager.)
"""

import argparse

from AppKit import NSPasteboard, NSPasteboardTypeString

CONCEALED = "org.nspasteboard.ConcealedType"
TRANSIENT = "org.nspasteboard.TransientType"

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("text", nargs="?", default="not-a-real-password-123")
parser.add_argument("--transient", action="store_true", help="use TransientType")
args = parser.parse_args()

marker = TRANSIENT if args.transient else CONCEALED
pb = NSPasteboard.generalPasteboard()
pb.clearContents()
pb.declareTypes_owner_([NSPasteboardTypeString, marker], None)
pb.setString_forType_(args.text, NSPasteboardTypeString)
pb.setString_forType_("", marker)
print(f"Copied {args.text!r} marked {marker}. It should NOT appear in clipmgr.")
