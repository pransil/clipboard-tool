"""The login helper's small floating panel (top-right of the screen).

The panel never becomes the key window, so keyboard focus stays in the login
form the user is filling in. Its rows and buttons accept the first click
without taking focus, so clicking "Username" pastes straight into that form.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSBezierPath,
    NSButton,
    NSColor,
    NSControlSizeSmall,
    NSEvent,
    NSFont,
    NSFontWeightRegular,
    NSFontWeightSemibold,
    NSInsetRect,
    NSLineBreakByTruncatingTail,
    NSMakeRect,
    NSPanel,
    NSPointInRect,
    NSScreen,
    NSStatusWindowLevel,
    NSTextAlignmentCenter,
    NSTextAlignmentRight,
    NSTextField,
    NSView,
    NSVisualEffectBlendingModeBehindWindow,
    NSVisualEffectMaterialPopover,
    NSVisualEffectStateActive,
    NSVisualEffectView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowStyleMaskFullSizeContentView,
    NSWindowStyleMaskNonactivatingPanel,
    NSWindowStyleMaskTitled,
    NSWindowTitleHidden,
)
from Foundation import NSObject

from ..login import FIELDS, LABELS, PASSWORD, USERNAME, LoginSession, Phase

WIDTH = 320
HEADER_H = 30
ROW_H = 28
ROW_GAP = 2
FOOTER_H = 36
HEIGHT = HEADER_H + 2 * ROW_H + ROW_GAP + 6 + FOOTER_H
SCREEN_MARGIN = 12
MESSAGE_SECONDS = 1.6
COPY_PROMPT = "← copy it now"


def _label(text, font, color, frame, align=None) -> NSTextField:
    field = NSTextField.labelWithString_(text)
    field.setFont_(font)
    field.setTextColor_(color)
    field.setFrame_(frame)
    field.setLineBreakMode_(NSLineBreakByTruncatingTail)
    field.cell().setUsesSingleLineMode_(True)
    if align is not None:
        field.setAlignment_(align)
    return field


def format_remaining(seconds: float) -> str:
    whole = max(0, math.ceil(seconds))
    return f"{whole // 60}:{whole % 60:02d}"


class CMHUDPanel(NSPanel):
    def canBecomeKeyWindow(self):
        return False

    def canBecomeMainWindow(self):
        return False


class CMHUDButton(NSButton):
    def acceptsFirstMouse_(self, event):
        return True


class CMHUDRow(NSView):
    """A row that can be clicked without taking keyboard focus."""

    def acceptsFirstMouse_(self, event):
        return True

    def drawRect_(self, rect):
        if not getattr(self, "on_click", None):
            return
        color = (
            NSColor.controlAccentColor().colorWithAlphaComponent_(0.35)
            if getattr(self, "pressed", False)
            else NSColor.quaternaryLabelColor()
        )
        color.setFill()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSInsetRect(self.bounds(), 0, 1), 6, 6
        ).fill()

    def mouseDown_(self, event):
        if getattr(self, "on_click", None):
            self.pressed = True
            self.setNeedsDisplay_(True)

    def mouseUp_(self, event):
        if not getattr(self, "pressed", False):
            return
        self.pressed = False
        self.setNeedsDisplay_(True)
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        if NSPointInRect(point, self.bounds()):
            self.on_click()


class LoginHUDController(NSObject):
    @objc.python_method
    def setup(
        self,
        session: LoginSession,
        hotkey_display: str,
        on_paste: Callable[[str], None],
        on_swap: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> LoginHUDController:
        self.session = session
        self.hotkey_display = hotkey_display
        self.on_paste = on_paste
        self.on_swap = on_swap
        self.on_cancel = on_cancel
        self.notice: str | None = None
        self.message: str | None = None
        self.countdown = None
        self._build_panel()
        return self

    # ----- public API ----------------------------------------------------

    @objc.python_method
    def is_visible(self) -> bool:
        return bool(self.panel.isVisible())

    @objc.python_method
    def show(self) -> None:
        NSObject.cancelPreviousPerformRequestsWithTarget_selector_object_(
            self, "hideAfterMessage:", None
        )
        self.message = None
        self.notice = None
        self.refresh()
        self._position()
        self.panel.orderFrontRegardless()

    @objc.python_method
    def refresh(self) -> None:
        """Redraw after a state change."""
        self._render()

    @objc.python_method
    def tick(self) -> None:
        """Update only the countdown (cheap; safe during a click)."""
        if self.countdown is not None and self.session.active:
            self.countdown.setStringValue_(format_remaining(self.session.remaining()))

    @objc.python_method
    def set_notice(self, text: str | None) -> None:
        self.notice = text
        self._render()

    @objc.python_method
    def finish(self, message: str, seconds: float | None = None) -> None:
        """Show a short closing message, then hide."""
        self.message = message
        self.notice = None
        self._render()
        if not self.panel.isVisible():
            self._position()
            self.panel.orderFrontRegardless()
        NSObject.cancelPreviousPerformRequestsWithTarget_selector_object_(
            self, "hideAfterMessage:", None
        )
        self.performSelector_withObject_afterDelay_(
            "hideAfterMessage:", None, seconds or MESSAGE_SECONDS
        )

    @objc.python_method
    def hide(self) -> None:
        self.panel.orderOut_(None)

    def hideAfterMessage_(self, _):
        if not self.session.active:
            self.hide()

    # ----- layout --------------------------------------------------------

    @objc.python_method
    def _build_panel(self) -> None:
        style = (
            NSWindowStyleMaskNonactivatingPanel
            | NSWindowStyleMaskTitled
            | NSWindowStyleMaskFullSizeContentView
        )
        panel = CMHUDPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, WIDTH, HEIGHT), style, NSBackingStoreBuffered, False
        )
        panel.setTitle_("Login")
        panel.setTitlebarAppearsTransparent_(True)
        panel.setTitleVisibility_(NSWindowTitleHidden)
        panel.setFloatingPanel_(True)
        panel.setBecomesKeyOnlyIfNeeded_(True)
        panel.setLevel_(NSStatusWindowLevel)
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        panel.setHidesOnDeactivate_(False)
        panel.setReleasedWhenClosed_(False)
        panel.setMovableByWindowBackground_(True)

        content = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, HEIGHT))
        content.setMaterial_(NSVisualEffectMaterialPopover)
        content.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        content.setState_(NSVisualEffectStateActive)
        panel.setContentView_(content)
        self.panel = panel

    @objc.python_method
    def _position(self) -> None:
        mouse = NSEvent.mouseLocation()
        screen = next(
            (s for s in NSScreen.screens() if NSPointInRect(mouse, s.frame())),
            NSScreen.mainScreen(),
        )
        visible = screen.visibleFrame()
        x = visible.origin.x + visible.size.width - WIDTH - SCREEN_MARGIN
        top = visible.origin.y + visible.size.height - SCREEN_MARGIN
        self.panel.setFrameTopLeftPoint_((x, top))

    @objc.python_method
    def _render(self) -> None:
        content = self.panel.contentView()
        for view in list(content.subviews()):
            view.removeFromSuperview()
        self.countdown = None
        session = self.session

        title = "🔑 Login ready" if session.ready else "🔑 Login"
        content.addSubview_(
            _label(
                title,
                NSFont.systemFontOfSize_weight_(13, NSFontWeightSemibold),
                NSColor.labelColor(),
                NSMakeRect(14, HEIGHT - 23, 200, 17),
            )
        )

        if self.message is not None:
            content.addSubview_(
                _label(
                    self.message,
                    NSFont.systemFontOfSize_(13),
                    NSColor.secondaryLabelColor(),
                    NSMakeRect(14, (HEIGHT - HEADER_H) / 2 - 9, WIDTH - 28, 18),
                    NSTextAlignmentCenter,
                )
            )
            return

        self.countdown = _label(
            format_remaining(session.remaining()),
            NSFont.monospacedDigitSystemFontOfSize_weight_(12, NSFontWeightRegular),
            NSColor.secondaryLabelColor(),
            NSMakeRect(WIDTH - 14 - 60, HEIGHT - 23, 60, 17),
            NSTextAlignmentRight,
        )
        content.addSubview_(self.countdown)

        top = HEIGHT - HEADER_H
        for index, field in enumerate(FIELDS):
            y = top - (index + 1) * ROW_H - index * ROW_GAP
            content.addSubview_(self._row(field, y))

        self._footer(content)

    @objc.python_method
    def _row(self, field: str, y: float) -> NSView:
        session = self.session
        width = WIDTH - 16
        row = CMHUDRow.alloc().initWithFrame_(NSMakeRect(8, y, width, ROW_H))
        row.on_click = None
        value_color = NSColor.labelColor()

        if session.ready:
            if session.next_field() == field:
                marker = f"{self.hotkey_display} →"
            elif session.is_pasted(field):
                marker = "✓"
            else:
                marker = ""
            value = session.masked(field)
            row.on_click = lambda f=field: self.on_paste(f)
            row.setToolTip_(f"Click to paste the {LABELS[field].lower()}")
        else:
            waiting_for = USERNAME if session.phase is Phase.CAPTURE_USERNAME else PASSWORD
            if session.has(field):
                marker, value = "✓", session.masked(field)
            elif field == waiting_for:
                marker, value = ("①" if field == USERNAME else "②"), COPY_PROMPT
                value_color = NSColor.controlAccentColor()
            else:
                marker, value = ("①" if field == USERNAME else "②"), ""

        font = NSFont.systemFontOfSize_(13)
        row.addSubview_(
            _label(
                marker,
                NSFont.systemFontOfSize_weight_(12, NSFontWeightSemibold),
                NSColor.secondaryLabelColor(),
                NSMakeRect(6, 5, 58, 18),
                NSTextAlignmentRight,
            )
        )
        row.addSubview_(
            _label(LABELS[field], font, NSColor.labelColor(), NSMakeRect(72, 5, 80, 18))
        )
        row.addSubview_(
            _label(value, font, value_color, NSMakeRect(156, 5, width - 162, 18))
        )
        return row

    @objc.python_method
    def _footer(self, content: NSView) -> None:
        session = self.session
        right_title, right_action = ("Clear", "clear:") if session.ready else ("Cancel", "clear:")
        right = self._button(right_title, right_action)
        right.setFrameOrigin_((WIDTH - 12 - right.frame().size.width, 9))
        content.addSubview_(right)

        left_edge = 14
        if self.notice:
            content.addSubview_(
                _label(
                    self.notice,
                    NSFont.systemFontOfSize_weight_(11, NSFontWeightSemibold),
                    NSColor.controlAccentColor(),
                    NSMakeRect(left_edge, 12, WIDTH - 28 - right.frame().size.width, 15),
                )
            )
        elif session.ready and not any(session.is_pasted(f) for f in FIELDS):
            swap = self._button("⇅ Swap", "swap:")
            swap.setFrameOrigin_((left_edge - 4, 9))
            content.addSubview_(swap)
        elif session.capturing:
            content.addSubview_(
                _label(
                    "Copy them from anywhere",
                    NSFont.systemFontOfSize_(11),
                    NSColor.secondaryLabelColor(),
                    NSMakeRect(left_edge, 12, WIDTH - 28 - right.frame().size.width, 15),
                )
            )

    @objc.python_method
    def _button(self, title: str, action: str) -> NSButton:
        button = CMHUDButton.buttonWithTitle_target_action_(title, self, action)
        button.setControlSize_(NSControlSizeSmall)
        button.setFont_(NSFont.systemFontOfSize_(11))
        button.sizeToFit()
        return button

    # ----- actions ---------------------------------------------------------

    def swap_(self, sender):
        self.on_swap()

    def clear_(self, sender):
        self.on_cancel()
