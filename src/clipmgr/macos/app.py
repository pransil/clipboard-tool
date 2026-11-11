"""Menu bar app: wires the clipboard watcher, hotkey, popup and paste together.

Everything runs on the main thread: an NSTimer polls the clipboard, Carbon
delivers hotkey presses through the main run loop, and the popup is AppKit.
Clipboard history is held in memory only and is gone when the app quits.
"""

from __future__ import annotations

import logging
import sys

import objc
from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSEventModifierFlagCommand,
    NSEventModifierFlagControl,
    NSEventModifierFlagOption,
    NSEventModifierFlagShift,
    NSImage,
    NSMenu,
    NSMenuItem,
    NSRunningApplication,
    NSStatusBar,
    NSVariableStatusItemLength,
    NSWorkspace,
)
from Foundation import NSObject, NSRunLoop, NSRunLoopCommonModes, NSTimer
from PyObjCTools import AppHelper

from .. import config as cfg
from ..history import History
from ..watcher import ClipboardWatcher
from . import paste
from .hotkey import HotkeyCenter, HotkeyError
from .pasteboard import Pasteboard
from .popup import PopupController

log = logging.getLogger("clipmgr")


def _app() -> NSApplication:
    return NSApplication.sharedApplication()

PASTE_DELAY = 0.08            # seconds between closing the popup and ⌘V
PASTE_DELAY_REACTIVATE = 0.2  # longer when focus had to be handed back
NOTICE_SECONDS = 3.0

_CARBON_TO_NS_FLAGS = {
    cfg.CMD: NSEventModifierFlagCommand,
    cfg.SHIFT: NSEventModifierFlagShift,
    cfg.OPTION: NSEventModifierFlagOption,
    cfg.CTRL: NSEventModifierFlagControl,
}


class AppDelegate(NSObject):
    @objc.python_method
    def setup(self, config: cfg.Config) -> AppDelegate:
        self.config = config
        self.history = History()
        self.pasteboard = Pasteboard()
        self.watcher = ClipboardWatcher(
            self.pasteboard.change_count, self.pasteboard.snapshot, self.history
        )
        self.popup = PopupController.alloc().init().setup(self.history, self.paste_item)
        self.hotkeys: HotkeyCenter | None = None
        self.previous_app: NSRunningApplication | None = None
        return self

    # ----- lifecycle -------------------------------------------------------

    def applicationDidFinishLaunching_(self, notification):
        _app().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        self._build_status_item()
        self._start_polling()
        self._register_hotkey()
        if not paste.is_trusted(prompt=False):
            self._explain_accessibility()
        log.info("clipmgr running. Hotkey: %s", self.config.hotkey.display)

    def applicationWillTerminate_(self, notification):
        if self.hotkeys is not None:
            self.hotkeys.close()
        self.history.clear_all()

    # ----- status item -----------------------------------------------------

    @objc.python_method
    def _build_status_item(self) -> None:
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        button = self.status_item.button()
        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            "doc.on.clipboard", "Clipboard history"
        )
        if image is not None:
            image.setTemplate_(True)
            button.setImage_(image)
        else:
            button.setTitle_("📋")
        button.setToolTip_(f"Clipboard history ({self.config.hotkey.display})")

        menu = NSMenu.alloc().initWithTitle_("clipmgr")
        menu.setDelegate_(self)
        menu.setAutoenablesItems_(False)

        show = self._menu_item("Show Clipboard History", "showPopup:")
        show.setKeyEquivalent_(self.config.hotkey.key if len(self.config.hotkey.key) == 1 else "")
        show.setKeyEquivalentModifierMask_(self._ns_modifier_mask())
        menu.addItem_(show)
        menu.addItem_(NSMenuItem.separatorItem())
        self.clear_item = self._menu_item("Clear History", "clearHistory:")
        menu.addItem_(self.clear_item)
        self.clear_all_item = self._menu_item("Clear Everything", "clearEverything:")
        menu.addItem_(self.clear_all_item)
        menu.addItem_(NSMenuItem.separatorItem())
        self.accessibility_item = self._menu_item(
            "Enable Auto-Paste (Accessibility)…", "grantAccessibility:"
        )
        menu.addItem_(self.accessibility_item)
        quit_item = self._menu_item("Quit clipmgr", "quit:")
        quit_item.setKeyEquivalent_("q")
        menu.addItem_(quit_item)
        self.status_item.setMenu_(menu)

    @objc.python_method
    def _menu_item(self, title: str, action: str) -> NSMenuItem:
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
        item.setTarget_(self)
        return item

    @objc.python_method
    def _ns_modifier_mask(self) -> int:
        mask = 0
        for carbon, ns in _CARBON_TO_NS_FLAGS.items():
            if self.config.hotkey.modifiers & carbon:
                mask |= ns
        return mask

    def menuNeedsUpdate_(self, menu):
        recent, pinned = len(self.history.recent), len(self.history.pinned)
        self.clear_item.setTitle_(f"Clear History ({recent})" if recent else "Clear History")
        self.clear_item.setEnabled_(recent > 0)
        self.clear_all_item.setEnabled_(recent + pinned > 0)
        self.accessibility_item.setHidden_(paste.is_trusted(prompt=False))

    @objc.python_method
    def _show_notice(self, text: str) -> None:
        button = self.status_item.button()
        button.setTitle_(f" {text}")
        NSObject.cancelPreviousPerformRequestsWithTarget_selector_object_(
            self, "clearNotice:", None
        )
        self.performSelector_withObject_afterDelay_("clearNotice:", None, NOTICE_SECONDS)

    def clearNotice_(self, _):
        self.status_item.button().setTitle_("")

    # ----- menu actions ------------------------------------------------------

    def showPopup_(self, sender):
        self.toggle_popup()

    def clearHistory_(self, sender):
        self.history.clear_history()
        self._refresh_popup()

    def clearEverything_(self, sender):
        self.history.clear_all()
        self._refresh_popup()

    def grantAccessibility_(self, sender):
        if not paste.is_trusted(prompt=True):
            paste.open_accessibility_settings()

    def quit_(self, sender):
        _app().terminate_(None)

    # ----- clipboard polling ---------------------------------------------------

    @objc.python_method
    def _start_polling(self) -> None:
        self.timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            self.config.poll_interval, self, "poll:", None, True
        )
        # Common modes: keep polling while a menu is open.
        NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSRunLoopCommonModes)
        self.watcher.poll()

    def poll_(self, timer):
        try:
            if self.watcher.poll():
                log.debug("history: %d recent, %d pinned",
                          len(self.history.recent), len(self.history.pinned))
                self._refresh_popup()
        except Exception:
            log.exception("clipboard poll failed")

    # ----- hotkey and popup ----------------------------------------------------

    @objc.python_method
    def _register_hotkey(self) -> None:
        hotkey = self.config.hotkey
        try:
            self.hotkeys = HotkeyCenter()
            self.hotkeys.register(hotkey.key_code, hotkey.modifiers, self.toggle_popup)
        except HotkeyError as exc:
            log.error("Could not register hotkey %s: %s", hotkey.display, exc)
            self._alert(
                f"Couldn't register the {hotkey.display} shortcut",
                f"{exc}.\n\nYou can still open the history from the clipboard icon in "
                f"the menu bar, or choose another shortcut in {cfg.CONFIG_PATH}.",
                ["OK"],
            )

    @objc.python_method
    def toggle_popup(self) -> None:
        if self.popup.is_visible():
            self.popup.close()
            return
        self.watcher.poll()  # pick up a copy made in the last fraction of a second
        self.previous_app = NSWorkspace.sharedWorkspace().frontmostApplication()
        self.popup.show()

    @objc.python_method
    def _refresh_popup(self) -> None:
        if self.popup.is_visible():
            selected = self.popup._selected_row()
            self.popup.reload(select=selected.item.id if selected else None)

    # ----- paste ------------------------------------------------------------

    @objc.python_method
    def paste_item(self, item_id: int) -> None:
        text = self.history.select(item_id)
        self.watcher.ignore(self.pasteboard.write_text(text))
        self.popup.close()
        if not paste.is_trusted(prompt=False):
            self._show_notice("Copied — press ⌘V")
            return
        delay = PASTE_DELAY
        if _app().isActive() and self.previous_app is not None:
            # Normally the non-activating panel leaves the other app frontmost.
            # If clipmgr did become active, hand focus back first.
            _app().yieldActivationToApplication_(self.previous_app)
            self.previous_app.activateWithOptions_(0)
            delay = PASTE_DELAY_REACTIVATE
        self.performSelector_withObject_afterDelay_("sendPaste:", None, delay)

    def sendPaste_(self, _):
        paste.send_cmd_v()

    # ----- permissions -----------------------------------------------------------

    @objc.python_method
    def _explain_accessibility(self) -> None:
        choice = self._alert(
            "Allow clipmgr to paste for you",
            "clipmgr pastes the item you pick by sending ⌘V to the app you were "
            "using. macOS needs the Accessibility permission for that.\n\n"
            f"The {self.config.hotkey.display} shortcut itself needs no permission, "
            "and clipmgr does not need Input Monitoring.\n\n"
            "When clipmgr runs from a terminal, macOS lists the terminal app "
            "(Terminal, iTerm, VS Code…) in Privacy & Security → Accessibility; turn "
            "that one on, then restart clipmgr.\n\n"
            "Without it, picking an item still copies it, and you press ⌘V yourself.",
            ["Open Accessibility Settings", "Not Now"],
        )
        if choice == NSAlertFirstButtonReturn:
            if not paste.is_trusted(prompt=True):
                paste.open_accessibility_settings()

    @objc.python_method
    def _alert(self, title: str, body: str, buttons: list[str]) -> int:
        alert = NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(body)
        for label in buttons:
            alert.addButtonWithTitle_(label)
        _app().activate()
        return alert.runModal()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s clipmgr %(levelname)s: %(message)s"
    )
    try:
        config = cfg.load_config()
    except cfg.ConfigError as exc:
        print(f"clipmgr: config error: {exc}; using defaults.", file=sys.stderr)
        config = cfg.Config(
            hotkey=cfg.parse_hotkey(cfg.DEFAULT_HOTKEY),
            poll_interval=cfg.DEFAULT_POLL_INTERVAL,
        )
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init().setup(config)
    app.setDelegate_(delegate)
    # NSApp holds its delegate weakly; keep a strong reference for the run.
    main.delegate = delegate
    AppHelper.runEventLoop(installInterrupt=True)
