"""The history popup: a floating, non-activating panel with a table of items.

A non-activating panel can take keyboard focus without making clipmgr the
active app, so the app the user was typing in stays frontmost. When the panel
closes, focus goes straight back there and a synthesized ⌘V lands in the
right place.
"""

from __future__ import annotations

from collections.abc import Callable

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSBezierPath,
    NSButton,
    NSColor,
    NSEvent,
    NSEventModifierFlagCommand,
    NSEventModifierFlagControl,
    NSEventModifierFlagOption,
    NSFocusRingTypeNone,
    NSFont,
    NSFontWeightMedium,
    NSFontWeightSemibold,
    NSInsetRect,
    NSLineBreakByTruncatingTail,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
    NSPanel,
    NSPointInRect,
    NSScreen,
    NSScrollView,
    NSStatusWindowLevel,
    NSTableColumn,
    NSTableRowView,
    NSTableView,
    NSTableViewSelectionHighlightStyleNone,
    NSTableViewStylePlain,
    NSTextAlignmentCenter,
    NSTextAlignmentRight,
    NSTextField,
    NSView,
    NSViewHeightSizable,
    NSViewMaxYMargin,
    NSViewMinXMargin,
    NSViewMinYMargin,
    NSViewWidthSizable,
    NSVisualEffectBlendingModeBehindWindow,
    NSVisualEffectMaterialPopover,
    NSVisualEffectStateActive,
    NSVisualEffectView,
    NSWindowCloseButton,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowMiniaturizeButton,
    NSWindowStyleMaskFullSizeContentView,
    NSWindowStyleMaskNonactivatingPanel,
    NSWindowStyleMaskTitled,
    NSWindowTitleHidden,
    NSWindowZoomButton,
    NSIndexSet,
)
from Foundation import NSObject

from ..display import (
    Row,
    build_rows,
    default_selection,
    item_for_key,
    next_selectable,
    row_for_item,
    tooltip,
)
from ..history import History

WIDTH = 560
TOP_H = 34          # title area (the transparent title bar)
FOOTER_H = 62
ITEM_ROW_H = 26
HEADER_ROW_H = 22
MAX_LIST_H = 440
MIN_LIST_H = ITEM_ROW_H * 2

HINT = "1–0 / a–z paste  ·  ↑↓ ⏎  ·  click  ·  ⌘P pin  ·  ⌫ delete  ·  esc close"

# Hardware key codes (HIToolbox/Events.h)
KEY_RETURN, KEY_ENTER, KEY_ESCAPE = 36, 76, 53
KEY_DELETE, KEY_FORWARD_DELETE = 51, 117
KEY_UP, KEY_DOWN, KEY_HOME, KEY_END = 126, 125, 115, 119
SELECT_BLOCKING_MODS = (
    NSEventModifierFlagCommand | NSEventModifierFlagControl | NSEventModifierFlagOption
)


def _label(text: str, font, color, frame) -> NSTextField:
    field = NSTextField.labelWithString_(text)
    field.setFont_(font)
    field.setTextColor_(color)
    field.setFrame_(frame)
    field.setLineBreakMode_(NSLineBreakByTruncatingTail)
    field.cell().setUsesSingleLineMode_(True)
    return field


class CMPanel(NSPanel):
    def canBecomeKeyWindow(self):
        return True

    def canBecomeMainWindow(self):
        return False


class CMRowView(NSTableRowView):
    """Rounded, lightly tinted selection that keeps text in normal colors."""

    def drawSelectionInRect_(self, rect):
        if self.selectionHighlightStyle() == NSTableViewSelectionHighlightStyleNone:
            return
        NSColor.controlAccentColor().colorWithAlphaComponent_(0.28).setFill()
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSInsetRect(self.bounds(), 4, 1), 6, 6
        )
        path.fill()

    def interiorBackgroundStyle(self):
        return 0  # NSBackgroundStyleNormal: don't flip text to white


class CMTableView(NSTableView):
    """Routes keystrokes to the popup controller before default handling."""

    def keyDown_(self, event):
        controller = getattr(self, "controller", None)
        if controller is not None and controller.handle_key(event):
            return
        objc.super(CMTableView, self).keyDown_(event)

    def performKeyEquivalent_(self, event):
        controller = getattr(self, "controller", None)
        if controller is not None and controller.handle_command_key(event):
            return True
        return objc.super(CMTableView, self).performKeyEquivalent_(event)


class PopupController(NSObject):
    """Owns the panel and table; mutates History in response to the user."""

    @objc.python_method
    def setup(
        self,
        history: History,
        on_paste: Callable[[int], None],
        on_change: Callable[[], None] | None = None,
    ) -> PopupController:
        self.history = history
        self.on_paste = on_paste
        self.on_change = on_change or (lambda: None)
        self.rows: list[Row] = []
        self._build_panel()
        return self

    # ----- public API ----------------------------------------------------

    @objc.python_method
    def is_visible(self) -> bool:
        return bool(self.panel.isVisible())

    @objc.python_method
    def show(self) -> None:
        self.reload(select=None)
        self._position_on_active_screen()
        self.panel.makeKeyAndOrderFront_(None)
        self.panel.makeFirstResponder_(self.table)

    @objc.python_method
    def close(self) -> None:
        if self.panel.isVisible():
            self.panel.orderOut_(None)

    @objc.python_method
    def toggle(self) -> None:
        if self.is_visible():
            self.close()
        else:
            self.show()

    @objc.python_method
    def reload(self, select: int | None = None) -> None:
        """Rebuild rows. ``select`` is an item id to keep highlighted."""
        self.rows = build_rows(self.history)
        self.table.reloadData()
        row = row_for_item(self.rows, select) if select is not None else None
        if row is None:
            row = default_selection(self.rows)
        self._select_row(row)
        self._resize()

    # ----- layout --------------------------------------------------------

    @objc.python_method
    def _build_panel(self) -> None:
        height = TOP_H + MIN_LIST_H + FOOTER_H
        style = (
            NSWindowStyleMaskNonactivatingPanel
            | NSWindowStyleMaskTitled
            | NSWindowStyleMaskFullSizeContentView
        )
        panel = CMPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, WIDTH, height), style, NSBackingStoreBuffered, False
        )
        panel.setTitle_("Clipboard")
        panel.setTitlebarAppearsTransparent_(True)
        panel.setTitleVisibility_(NSWindowTitleHidden)
        for kind in (NSWindowCloseButton, NSWindowMiniaturizeButton, NSWindowZoomButton):
            button = panel.standardWindowButton_(kind)
            if button is not None:
                button.setHidden_(True)
        panel.setFloatingPanel_(True)
        panel.setLevel_(NSStatusWindowLevel)
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        panel.setHidesOnDeactivate_(False)
        panel.setBecomesKeyOnlyIfNeeded_(False)
        panel.setReleasedWhenClosed_(False)
        panel.setMovableByWindowBackground_(True)
        panel.setDelegate_(self)

        content = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, height))
        content.setMaterial_(NSVisualEffectMaterialPopover)
        content.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        content.setState_(NSVisualEffectStateActive)
        panel.setContentView_(content)

        title = _label(
            "Clipboard History",
            NSFont.systemFontOfSize_weight_(13, NSFontWeightSemibold),
            NSColor.labelColor(),
            NSMakeRect(16, height - 26, WIDTH - 32, 18),
        )
        title.setAlignment_(NSTextAlignmentCenter)
        title.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        content.addSubview_(title)

        scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(8, FOOTER_H, WIDTH - 16, height - TOP_H - FOOTER_H)
        )
        scroll.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        scroll.setDrawsBackground_(False)
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)

        table = CMTableView.alloc().initWithFrame_(scroll.bounds())
        table.controller = self
        column = NSTableColumn.alloc().initWithIdentifier_("main")
        column.setWidth_(WIDTH - 16)
        table.addTableColumn_(column)
        table.setHeaderView_(None)
        table.setStyle_(NSTableViewStylePlain)
        table.setBackgroundColor_(NSColor.clearColor())
        table.setIntercellSpacing_((0, 0))
        table.setFocusRingType_(NSFocusRingTypeNone)
        table.setAllowsEmptySelection_(True)
        table.setAllowsMultipleSelection_(False)
        table.setDataSource_(self)
        table.setDelegate_(self)
        table.setTarget_(self)
        table.setAction_("rowClicked:")
        table.setMenu_(self._context_menu())
        table.sizeLastColumnToFit()
        scroll.setDocumentView_(table)
        content.addSubview_(scroll)

        hint = _label(
            HINT,
            NSFont.systemFontOfSize_(11),
            NSColor.secondaryLabelColor(),
            NSMakeRect(16, 38, WIDTH - 32, 16),
        )
        hint.setAlignment_(NSTextAlignmentCenter)
        hint.setAutoresizingMask_(NSViewWidthSizable | NSViewMaxYMargin)
        content.addSubview_(hint)

        clear_all = NSButton.buttonWithTitle_target_action_("Clear everything", self, "clearAll:")
        clear_all.sizeToFit()
        all_w = clear_all.frame().size.width
        clear_all.setFrameOrigin_((WIDTH - 16 - all_w, 8))
        clear_all.setAutoresizingMask_(NSViewMinXMargin | NSViewMaxYMargin)
        content.addSubview_(clear_all)

        clear = NSButton.buttonWithTitle_target_action_("Clear history", self, "clearHistory:")
        clear.sizeToFit()
        clear_w = clear.frame().size.width
        clear.setFrameOrigin_((WIDTH - 16 - all_w - 8 - clear_w, 8))
        clear.setAutoresizingMask_(NSViewMinXMargin | NSViewMaxYMargin)
        content.addSubview_(clear)

        count = _label(
            "",
            NSFont.systemFontOfSize_(11),
            NSColor.secondaryLabelColor(),
            NSMakeRect(16, 13, 220, 16),
        )
        count.setAutoresizingMask_(NSViewMaxYMargin)
        content.addSubview_(count)

        self.panel, self.table, self.count_label = panel, table, count

    @objc.python_method
    def _context_menu(self) -> NSMenu:
        menu = NSMenu.alloc().initWithTitle_("Item")
        menu.setDelegate_(self)
        for title, action in (
            ("Paste", "menuPaste:"),
            ("Pin", "menuTogglePin:"),
            ("Delete", "menuDelete:"),
        ):
            entry = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
            entry.setTarget_(self)
            menu.addItem_(entry)
        return menu

    @objc.python_method
    def _list_height(self) -> float:
        total = sum(self._row_height(row) for row in self.rows)
        return max(MIN_LIST_H, min(MAX_LIST_H, total))

    @objc.python_method
    def _resize(self) -> None:
        height = TOP_H + self._list_height() + FOOTER_H
        frame = self.panel.frame()
        top = frame.origin.y + frame.size.height
        self.panel.setFrame_display_(
            NSMakeRect(frame.origin.x, top - height, WIDTH, height), True
        )
        pinned, recent = len(self.history.pinned), len(self.history.recent)
        parts = [f"{recent} recent"]
        if pinned:
            parts.insert(0, f"{pinned} pinned")
        self.count_label.setStringValue_(" · ".join(parts))

    @objc.python_method
    def _position_on_active_screen(self) -> None:
        mouse = NSEvent.mouseLocation()
        screen = next(
            (s for s in NSScreen.screens() if NSPointInRect(mouse, s.frame())),
            NSScreen.mainScreen(),
        )
        visible = screen.visibleFrame()
        frame = self.panel.frame()
        x = visible.origin.x + (visible.size.width - frame.size.width) / 2
        top = visible.origin.y + visible.size.height * 0.78
        self.panel.setFrameTopLeftPoint_((x, top))

    # ----- table data source / delegate ----------------------------------

    def numberOfRowsInTableView_(self, table):
        return len(self.rows)

    def tableView_heightOfRow_(self, table, row):
        return self._row_height(self.rows[row])

    def tableView_shouldSelectRow_(self, table, row):
        return 0 <= row < len(self.rows) and self.rows[row].selectable

    def tableView_rowViewForRow_(self, table, row):
        return CMRowView.alloc().init()

    def tableView_viewForTableColumn_row_(self, table, column, row):
        data = self.rows[row]
        width = table.bounds().size.width or (WIDTH - 16)
        height = self._row_height(data)
        view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, width, height))
        if data.kind == "header":
            label = _label(
                data.text,
                NSFont.systemFontOfSize_weight_(10, NSFontWeightSemibold),
                NSColor.secondaryLabelColor(),
                NSMakeRect(12, 3, width - 24, 14),
            )
            label.setAutoresizingMask_(NSViewWidthSizable)
            view.addSubview_(label)
        elif data.kind == "empty":
            label = _label(
                data.text,
                NSFont.systemFontOfSize_(13),
                NSColor.secondaryLabelColor(),
                NSMakeRect(12, 4, width - 24, 18),
            )
            label.setAlignment_(NSTextAlignmentCenter)
            label.setAutoresizingMask_(NSViewWidthSizable)
            view.addSubview_(label)
        else:
            key = _label(
                data.key,
                NSFont.monospacedSystemFontOfSize_weight_(13, NSFontWeightMedium),
                NSColor.secondaryLabelColor(),
                NSMakeRect(8, 4, 20, 18),
            )
            key.setAlignment_(NSTextAlignmentRight)
            view.addSubview_(key)
            text = _label(
                data.text,
                NSFont.systemFontOfSize_(13),
                NSColor.labelColor(),
                NSMakeRect(38, 4, width - 48, 18),
            )
            text.setAutoresizingMask_(NSViewWidthSizable)
            view.addSubview_(text)
            view.setToolTip_(tooltip(data.item.text))
        return view

    @objc.python_method
    def _row_height(self, row: Row) -> float:
        return HEADER_ROW_H if row.kind == "header" else ITEM_ROW_H

    # ----- window delegate ------------------------------------------------

    def windowDidResignKey_(self, notification):
        self.close()

    # ----- context menu ---------------------------------------------------

    def menuNeedsUpdate_(self, menu):
        row = self._clicked_row()
        item = row.item if row is not None else None
        for entry in menu.itemArray():
            entry.setEnabled_(item is not None)
            if entry.action() == "menuTogglePin:":
                entry.setTitle_("Unpin" if item is not None and item.pinned else "Pin")

    def menuPaste_(self, sender):
        row = self._clicked_row()
        if row is not None:
            self._paste(row)

    def menuTogglePin_(self, sender):
        row = self._clicked_row()
        if row is not None:
            self._toggle_pin(row)

    def menuDelete_(self, sender):
        row = self._clicked_row()
        if row is not None:
            self._delete(row)

    @objc.python_method
    def _clicked_row(self) -> Row | None:
        index = self.table.clickedRow()
        if 0 <= index < len(self.rows) and self.rows[index].selectable:
            return self.rows[index]
        return None

    # ----- actions ---------------------------------------------------------

    def rowClicked_(self, sender):
        row = self._clicked_row()
        if row is not None:
            self._paste(row)

    def clearHistory_(self, sender):
        self.history.clear_history()
        self._changed(select=None)

    def clearAll_(self, sender):
        self.history.clear_all()
        self._changed(select=None)

    @objc.python_method
    def handle_key(self, event) -> bool:
        code = event.keyCode()
        flags = event.modifierFlags()
        if code == KEY_ESCAPE:
            self.close()
            return True
        if code in (KEY_RETURN, KEY_ENTER):
            row = self._selected_row()
            if row is not None:
                self._paste(row)
            return True
        if code in (KEY_DELETE, KEY_FORWARD_DELETE):
            row = self._selected_row()
            if row is not None:
                self._delete(row)
            return True
        if code in (KEY_UP, KEY_DOWN, KEY_HOME, KEY_END):
            self._move_selection(code)
            return True
        if flags & SELECT_BLOCKING_MODS:
            return False
        chars = event.charactersIgnoringModifiers() or ""
        item = item_for_key(chars, self.history)
        if item is not None:
            index = row_for_item(self.rows, item.id)
            if index is not None:
                self._paste(self.rows[index])
            return True
        return False

    @objc.python_method
    def handle_command_key(self, event) -> bool:
        flags = event.modifierFlags()
        if not flags & NSEventModifierFlagCommand:
            return False
        chars = (event.charactersIgnoringModifiers() or "").lower()
        if chars == "p":
            row = self._selected_row()
            if row is not None:
                self._toggle_pin(row)
            return True
        if chars == "w":
            self.close()
            return True
        if event.keyCode() in (KEY_DELETE, KEY_FORWARD_DELETE):
            row = self._selected_row()
            if row is not None:
                self._delete(row)
            return True
        return False

    @objc.python_method
    def _selected_row(self) -> Row | None:
        index = self.table.selectedRow()
        if 0 <= index < len(self.rows) and self.rows[index].selectable:
            return self.rows[index]
        return None

    @objc.python_method
    def _select_row(self, index: int | None) -> None:
        if index is None:
            self.table.deselectAll_(None)
            return
        self.table.selectRowIndexes_byExtendingSelection_(
            NSIndexSet.indexSetWithIndex_(index), False
        )
        self.table.scrollRowToVisible_(index)

    @objc.python_method
    def _move_selection(self, code: int) -> None:
        current = self.table.selectedRow()
        if code == KEY_HOME:
            target = next_selectable(self.rows, -1, +1)
        elif code == KEY_END:
            target = next_selectable(self.rows, len(self.rows), -1)
        elif current < 0:
            target = default_selection(self.rows)
        else:
            step = -1 if code == KEY_UP else +1
            target = next_selectable(self.rows, current, step)
        if target is not None:
            self._select_row(target)

    @objc.python_method
    def _paste(self, row: Row) -> None:
        if row.item is not None:
            self.on_paste(row.item.id)

    @objc.python_method
    def _toggle_pin(self, row: Row) -> None:
        self.history.toggle_pin(row.item.id)
        self._changed(select=row.item.id)

    @objc.python_method
    def _delete(self, row: Row) -> None:
        index = self.rows.index(row)
        neighbour = next_selectable(self.rows, index, +1)
        if neighbour is None:
            neighbour = next_selectable(self.rows, index, -1)
        keep = self.rows[neighbour].item.id if neighbour is not None else None
        self.history.delete(row.item.id)
        self._changed(select=keep)

    @objc.python_method
    def _changed(self, select: int | None) -> None:
        self.reload(select=select)
        self.on_change()
