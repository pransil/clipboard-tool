"""Accessibility permission checks and synthesizing ⌘V.

Posting a keystroke into another app requires the Accessibility permission.
When clipmgr runs from a terminal, macOS attributes the permission to the
terminal app (Terminal, iTerm, VS Code...), so that is the app to enable.
"""

from __future__ import annotations

from AppKit import NSURL, NSWorkspace
from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventPost,
    CGEventSetFlags,
    CGEventSourceCreate,
    CGEventSourceFlagsState,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskControl,
    kCGEventFlagMaskShift,
    kCGEventSourceStateCombinedSessionState,
    kCGEventSourceStateHIDSystemState,
    kCGHIDEventTap,
)

KEY_V = 0x09  # kVK_ANSI_V: the physical V key on ANSI/QWERTY layouts
ACCESSIBILITY_SETTINGS_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
)


def is_trusted(prompt: bool = False) -> bool:
    """True if this process may post keystrokes. ``prompt`` shows the system dialog."""
    return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: prompt}))


def open_accessibility_settings() -> None:
    NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(ACCESSIBILITY_SETTINGS_URL))


def send_cmd_v() -> None:
    """Post ⌘V to whichever app has keyboard focus."""
    source = CGEventSourceCreate(kCGEventSourceStateCombinedSessionState)
    for key_down in (True, False):
        event = CGEventCreateKeyboardEvent(source, KEY_V, key_down)
        CGEventSetFlags(event, kCGEventFlagMaskCommand)
        CGEventPost(kCGHIDEventTap, event)


_MODIFIER_MASK = (
    kCGEventFlagMaskControl | kCGEventFlagMaskAlternate
    | kCGEventFlagMaskShift | kCGEventFlagMaskCommand
)


def modifiers_held() -> bool:
    """True while ⌃, ⌥, ⇧ or ⌘ is physically held down.

    A shortcut fires while its keys are still down; posting ⌘V before they are
    released could reach the app as e.g. ⌃⌘V, so callers wait for this first.
    """
    return bool(CGEventSourceFlagsState(kCGEventSourceStateHIDSystemState) & _MODIFIER_MASK)
