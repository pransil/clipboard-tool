"""Render the popup with sample data to docs/screenshot-{light,dark}.png.

    uv run python scripts/render_screenshots.py

Renders offscreen at 2x; no clipboard or screen-recording access needed.
"""

from pathlib import Path

from AppKit import (
    NSAppearance,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBezierPath,
    NSBitmapImageFileTypePNG,
    NSBitmapImageRep,
    NSCompositingOperationCopy,
    NSDeviceRGBColorSpace,
    NSGraphicsContext,
    NSMakeRect,
)

from clipmgr.history import History
from clipmgr.macos.popup import PopupController

DOCS = Path(__file__).resolve().parent.parent / "docs"
SCALE = 2
CORNER = 12

PINNED = [
    "ssh deploy@prod-01.example.com",
    "Thanks for reaching out — I'll get back to you by Friday.",
]
RECENT = [  # shown as 1, 2, ... 0
    "Meeting notes — Q4 planning",
    "https://example.com/docs/getting-started",
    'def greet(name):\n    return f"Hello, {name}!"',
    "SELECT id, email FROM users WHERE active = 1;",
    "+1 (555) 010-4477",
    "brew install uv",
    "Order #48213 shipped",
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor",
    "42",
    "git push -u origin main",
]


def new_rep(width: int, height: int) -> NSBitmapImageRep:
    return NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, width, height, 8, 4, True, False, NSDeviceRGBColorSpace, 0, 0
    )


def render(popup: PopupController, path: Path) -> None:
    view = popup.panel.contentView()
    bounds = view.bounds()
    w, h = int(bounds.size.width * SCALE), int(bounds.size.height * SCALE)

    flat = new_rep(w, h)
    flat.setSize_(bounds.size)
    view.cacheDisplayInRect_toBitmapImageRep_(bounds, flat)

    # Clip to the window's rounded corners, leaving them transparent.
    rounded = new_rep(w, h)
    rounded.setSize_(bounds.size)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(
        NSGraphicsContext.graphicsContextWithBitmapImageRep_(rounded)
    )
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(bounds, CORNER, CORNER).addClip()
    flat.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
        bounds, NSMakeRect(0, 0, 0, 0), NSCompositingOperationCopy, 1.0, True, None
    )
    NSGraphicsContext.restoreGraphicsState()

    data = rounded.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
    data.writeToFile_atomically_(str(path), True)
    print(f"wrote {path} ({w}x{h})")


def main() -> None:
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    history = History()
    for text in PINNED:
        history.add(text)
        history.pin(history.recent[0].id)
    for text in reversed(RECENT):
        history.add(text)

    popup = PopupController.alloc().init().setup(history, lambda _id: None)
    popup.show()
    DOCS.mkdir(exist_ok=True)
    for name, appearance in (("light", "NSAppearanceNameAqua"), ("dark", "NSAppearanceNameDarkAqua")):
        popup.panel.setAppearance_(NSAppearance.appearanceNamed_(appearance))
        popup.panel.contentView().displayIfNeeded()
        render(popup, DOCS / f"screenshot-{name}.png")
    popup.close()


if __name__ == "__main__":
    main()
