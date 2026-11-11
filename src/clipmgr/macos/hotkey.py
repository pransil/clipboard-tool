"""Global hotkeys via Carbon's RegisterEventHotKey, called through ctypes.

Unlike event taps (pynput, CGEventTap), RegisterEventHotKey needs no
Accessibility or Input Monitoring permission, and it consumes the keystroke so
the frontmost app does not also act on it. Events are delivered on the main
run loop, so callbacks run on the main thread and may touch AppKit.
"""

from __future__ import annotations

import ctypes
import logging
from collections.abc import Callable
from ctypes import CFUNCTYPE, POINTER, Structure, byref, c_int32, c_uint32, c_ulong, c_void_p, sizeof

log = logging.getLogger(__name__)


def fourcc(code: str) -> int:
    return int.from_bytes(code.encode("ascii"), "big")


class EventTypeSpec(Structure):
    _fields_ = [("eventClass", c_uint32), ("eventKind", c_uint32)]


class EventHotKeyID(Structure):
    _fields_ = [("signature", c_uint32), ("id", c_uint32)]


# OSStatus (*)(EventHandlerCallRef, EventRef, void *userData)
EventHandlerProc = CFUNCTYPE(c_int32, c_void_p, c_void_p, c_void_p)

kEventClassKeyboard = fourcc("keyb")
kEventHotKeyPressed = 5
kEventParamDirectObject = fourcc("----")
typeEventHotKeyID = fourcc("hkid")
noErr = 0
eventNotHandledErr = -9874
eventHotKeyExistsErr = -9878
eventHotKeyInvalidErr = -9879

_carbon = ctypes.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
_carbon.GetApplicationEventTarget.restype = c_void_p
_carbon.GetApplicationEventTarget.argtypes = []
_carbon.InstallEventHandler.restype = c_int32
_carbon.InstallEventHandler.argtypes = [
    c_void_p, EventHandlerProc, c_ulong, POINTER(EventTypeSpec), c_void_p, POINTER(c_void_p),
]
_carbon.RemoveEventHandler.restype = c_int32
_carbon.RemoveEventHandler.argtypes = [c_void_p]
_carbon.RegisterEventHotKey.restype = c_int32
_carbon.RegisterEventHotKey.argtypes = [
    c_uint32, c_uint32, EventHotKeyID, c_void_p, c_uint32, POINTER(c_void_p),
]
_carbon.UnregisterEventHotKey.restype = c_int32
_carbon.UnregisterEventHotKey.argtypes = [c_void_p]
_carbon.GetEventParameter.restype = c_int32
_carbon.GetEventParameter.argtypes = [
    c_void_p, c_uint32, c_uint32, POINTER(c_uint32), c_ulong, POINTER(c_ulong), c_void_p,
]


class HotkeyError(RuntimeError):
    pass


class HotkeyCenter:
    """Registers global hotkeys and dispatches presses to Python callbacks."""

    SIGNATURE = fourcc("CLPM")

    def __init__(self) -> None:
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._refs: dict[int, c_void_p] = {}
        self._next_id = 1
        # Keep the C callback alive for as long as the handler is installed.
        self._proc = EventHandlerProc(self._on_event)
        self._handler_ref = c_void_p()
        spec = EventTypeSpec(kEventClassKeyboard, kEventHotKeyPressed)
        status = _carbon.InstallEventHandler(
            _carbon.GetApplicationEventTarget(), self._proc, 1, byref(spec), None,
            byref(self._handler_ref),
        )
        if status != noErr:
            raise HotkeyError(f"InstallEventHandler failed (OSStatus {status})")

    def register(self, key_code: int, modifiers: int, callback: Callable[[], None]) -> int:
        hotkey_id = self._next_id
        self._next_id += 1
        ref = c_void_p()
        status = _carbon.RegisterEventHotKey(
            key_code, modifiers, EventHotKeyID(self.SIGNATURE, hotkey_id),
            _carbon.GetApplicationEventTarget(), 0, byref(ref),
        )
        if status == eventHotKeyExistsErr:
            raise HotkeyError("that shortcut is already registered by another app")
        if status != noErr:
            raise HotkeyError(f"RegisterEventHotKey failed (OSStatus {status})")
        self._callbacks[hotkey_id] = callback
        self._refs[hotkey_id] = ref
        return hotkey_id

    def unregister(self, hotkey_id: int) -> None:
        ref = self._refs.pop(hotkey_id, None)
        self._callbacks.pop(hotkey_id, None)
        if ref is not None:
            _carbon.UnregisterEventHotKey(ref)

    def close(self) -> None:
        for hotkey_id in list(self._refs):
            self.unregister(hotkey_id)
        if self._handler_ref:
            _carbon.RemoveEventHandler(self._handler_ref)
            self._handler_ref = c_void_p()

    def _on_event(self, _call_ref, event, _user_data) -> int:
        hotkey = EventHotKeyID()
        status = _carbon.GetEventParameter(
            event, kEventParamDirectObject, typeEventHotKeyID, None,
            sizeof(hotkey), None, byref(hotkey),
        )
        if status != noErr or hotkey.signature != self.SIGNATURE:
            return eventNotHandledErr
        callback = self._callbacks.get(hotkey.id)
        if callback is None:
            return eventNotHandledErr
        try:
            callback()
        except Exception:  # never let an exception unwind into Carbon
            log.exception("hotkey callback failed")
        return noErr
