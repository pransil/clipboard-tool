"""Menu bar app: wires the clipboard watcher, hotkeys, popup, login helper and paste.

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
from ..login import LABELS, LoginSession
from ..watcher import ClipboardWatcher
from . import paste
from .hotkey import HotkeyCenter, HotkeyError
from .login_hud import LoginHUDController
from .pasteboard import Pasteboard, SavedClipboard
from .popup import PopupController

log = logging.getLogger("clipmgr")


def _app() -> NSApplication:
    return NSApplication.sharedApplication()


PASTE_DELAY = 0.08            # seconds between closing the popup and ⌘V
PASTE_DELAY_REACTIVATE = 0.2  # longer when focus had to be handed back
NOTICE_SECONDS = 3.0

LOGIN_TICK = 0.5              # countdown refresh / timeout check
LOGIN_RESTORE_DELAY = 1.0     # after pasting a login value, restore the clipboard
MANUAL_PASTE_WINDOW = 15.0    # without Accessibility: time to press ⌘V yourself
MODIFIER_POLL = 0.03          # wait for the shortcut's keys to be released...
MODIFIER_WAIT_MAX = 2.0       # ...but not forever

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

        self.login = LoginSession(timeout=config.login_timeout)
        self.login_hud = LoginHUDController.alloc().init().setup(
            self.login,
            config.login_hotkey.display,
            on_paste=self.paste_login_field,
            on_swap=self.swap_login,
            on_cancel=self.cancel_login,
        )
        self._saved_clipboard: SavedClipboard | None = None
        self._login_timer = None
        self._paste_waiting: str | None = None
        self._keys_waited = 0.0
        self._pending_restores: dict[int, tuple[int, SavedClipboard]] = {}
        self._restore_token = 0
        return self

    # ----- lifecycle -------------------------------------------------------

    def applicationDidFinishLaunching_(self, notification):
        _app().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        self._build_status_item()
        self._start_polling()
        self._register_hotkeys()
        if not paste.is_trusted(prompt=False):
            self._explain_accessibility()
        log.info(
            "clipmgr running. History: %s  Login helper: %s",
            self.config.hotkey.display, self.config.login_hotkey.display,
        )

    def applicationWillTerminate_(self, notification):
        if self.hotkeys is not None:
            self.hotkeys.close()
        self.login.cancel()
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
        self._show_shortcut(show, self.config.hotkey)
        menu.addItem_(show)
        self.login_item = self._menu_item("Capture Login", "toggleLogin:")
        self._show_shortcut(self.login_item, self.config.login_hotkey)
        menu.addItem_(self.login_item)
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
    def _show_shortcut(self, item: NSMenuItem, hotkey: cfg.Hotkey) -> None:
        """Display a hotkey next to a menu item (the hotkey itself is global)."""
        if len(hotkey.key) != 1:
            return
        mask = 0
        for carbon, ns in _CARBON_TO_NS_FLAGS.items():
            if hotkey.modifiers & carbon:
                mask |= ns
        item.setKeyEquivalent_(hotkey.key)
        item.setKeyEquivalentModifierMask_(mask)

    def menuNeedsUpdate_(self, menu):
        recent, pinned = len(self.history.recent), len(self.history.pinned)
        self.clear_item.setTitle_(f"Clear History ({recent})" if recent else "Clear History")
        self.clear_item.setEnabled_(recent > 0)
        self.clear_all_item.setEnabled_(recent + pinned > 0 or self.login.active)
        self.login_item.setTitle_("Cancel Login" if self.login.active else "Capture Login")
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
        if self.login.active:
            self.cancel_login()

    def toggleLogin_(self, sender):
        if self.login.active:
            self.cancel_login()
        else:
            self.start_login()

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
    def _register_hotkeys(self) -> None:
        try:
            self.hotkeys = HotkeyCenter()
        except HotkeyError as exc:
            log.error("Could not install the hotkey handler: %s", exc)
            return
        for hotkey, callback, menu_name, setting in (
            (self.config.hotkey, self.toggle_popup, "Show Clipboard History", "hotkey"),
            (self.config.login_hotkey, self.login_hotkey_pressed, "Capture Login",
             "login_hotkey"),
        ):
            try:
                self.hotkeys.register(hotkey.key_code, hotkey.modifiers, callback)
            except HotkeyError as exc:
                log.error("Could not register hotkey %s: %s", hotkey.display, exc)
                self._alert(
                    f"Couldn't register the {hotkey.display} shortcut",
                    f"{exc}.\n\nYou can still use {menu_name} from the clipboard icon "
                    f"in the menu bar, or choose another `{setting}` in {cfg.CONFIG_PATH}.",
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

    # ----- login helper ---------------------------------------------------------
    #
    # ⌃⌘L starts capturing; the next two copies (password-manager copies
    # included) become the username and password instead of history items, and
    # the previous clipboard is put back right after each one. Then each ⌃⌘L
    # (or a click in the panel) pastes the next value. Everything is wiped after
    # the second paste, on cancel, or after the inactivity timeout.

    @objc.python_method
    def login_hotkey_pressed(self) -> None:
        if self._paste_waiting is not None:
            return  # a paste is already waiting for the shortcut keys to be released
        if not self.login.active:
            self.start_login()
        elif self.login.capturing:
            self.cancel_login("Login cancelled")
        else:
            self.paste_login_field(None)

    @objc.python_method
    def start_login(self) -> None:
        self.watcher.poll()  # a copy made just before starting belongs in history
        self._saved_clipboard = self.pasteboard.save()
        self.login.start()
        self.watcher.capture = self._on_login_copy
        self.login_hud.show()
        self._start_login_timer()
        log.info("login helper: waiting for username and password")

    @objc.python_method
    def _on_login_copy(self, text: str) -> None:
        field = self.login.capture(text)
        # Put the previous clipboard back so the value doesn't sit on it.
        self.watcher.ignore(self.pasteboard.restore(self._saved_clipboard or []))
        if not self.login.capturing:
            self.watcher.capture = None
        if field is not None:
            log.info("login helper: %s captured", field)  # never the value
        self.login_hud.refresh()

    @objc.python_method
    def paste_login_field(self, field: str | None) -> None:
        if not self.login.ready or self._paste_waiting is not None:
            return
        self._paste_waiting = field or self.login.next_field()
        self._keys_waited = 0.0
        self._paste_when_keys_released()

    @objc.python_method
    def _paste_when_keys_released(self) -> None:
        # The shortcut fires while ⌃⌘ are still down; wait so the app sees ⌘V.
        if paste.modifiers_held() and self._keys_waited < MODIFIER_WAIT_MAX:
            self._keys_waited += MODIFIER_POLL
            self.performSelector_withObject_afterDelay_("checkKeysReleased:", None, MODIFIER_POLL)
            return
        field, self._paste_waiting = self._paste_waiting, None
        if field is not None and self.login.ready:
            self._paste_login_value(field)

    def checkKeysReleased_(self, _):
        self._paste_when_keys_released()

    @objc.python_method
    def _paste_login_value(self, field: str) -> None:
        field, value, finished = self.login.take(field)
        saved = self._saved_clipboard or []
        count = self.pasteboard.write_secret(value)
        del value
        self.watcher.ignore(count)
        if paste.is_trusted(prompt=False):
            paste.send_cmd_v()
            self._schedule_restore(count, saved, LOGIN_RESTORE_DELAY)
            notice = None
        else:
            self._schedule_restore(count, saved, MANUAL_PASTE_WINDOW)
            notice = f"{LABELS[field]} copied — press ⌘V"
        log.info("login helper: %s pasted", field)
        if finished:
            self._end_login(notice or "✓ Done — login cleared", seconds=4.0 if notice else None)
        else:
            self.login_hud.set_notice(notice)

    @objc.python_method
    def _schedule_restore(self, count: int, saved: SavedClipboard, delay: float) -> None:
        self._restore_token += 1
        self._pending_restores[self._restore_token] = (count, saved)
        self.performSelector_withObject_afterDelay_(
            "restoreClipboard:", self._restore_token, delay
        )

    def restoreClipboard_(self, token):
        count, saved = self._pending_restores.pop(int(token), (None, None))
        # Only if the login value is still there (the user hasn't copied since).
        if count is not None and self.pasteboard.change_count() == count:
            self.watcher.ignore(self.pasteboard.restore(saved))

    @objc.python_method
    def swap_login(self) -> None:
        self.login.swap()
        self.login_hud.refresh()

    @objc.python_method
    def cancel_login(self, message: str = "Login cleared") -> None:
        if self.login.active:
            self._end_login(message)
        else:
            self.login_hud.hide()

    @objc.python_method
    def _end_login(self, message: str, seconds: float | None = None) -> None:
        self.login.cancel()
        self.watcher.capture = None
        self._saved_clipboard = None
        self._paste_waiting = None
        self._stop_login_timer()
        self.login_hud.finish(message, seconds)
        log.info("login helper: cleared")

    @objc.python_method
    def _start_login_timer(self) -> None:
        self._stop_login_timer()
        self._login_timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            LOGIN_TICK, self, "loginTick:", None, True
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(self._login_timer, NSRunLoopCommonModes)

    @objc.python_method
    def _stop_login_timer(self) -> None:
        if self._login_timer is not None:
            self._login_timer.invalidate()
            self._login_timer = None

    def loginTick_(self, timer):
        if self.login.expire_if_due():
            self._end_login("Login cleared (timed out)")
        else:
            self.login_hud.tick()

    # ----- permissions -----------------------------------------------------------

    @objc.python_method
    def _explain_accessibility(self) -> None:
        choice = self._alert(
            "Allow clipmgr to paste for you",
            "clipmgr pastes the item you pick by sending ⌘V to the app you were "
            "using. macOS needs the Accessibility permission for that.\n\n"
            f"The {self.config.hotkey.display} shortcut itself needs no permission, "
            "and clipmgr does not need Input Monitoring.\n\n"
            "In Privacy & Security → Accessibility, macOS lists whichever app started "
            "clipmgr: your terminal app (Terminal, iTerm, VS Code…) if you ran it from "
            "a terminal, or \"Python\" if it started at login. Turn that one on. If "
            "pasting still doesn't work, restart clipmgr.\n\n"
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
