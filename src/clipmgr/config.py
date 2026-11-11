"""Settings and hotkey parsing. Pure Python.

Settings are read from an optional TOML file (``~/.config/clipmgr/config.toml``)::

    hotkey = "ctrl+cmd+v"
    poll_interval = 0.25

The file only holds settings. Clipboard history is never written to disk.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOTKEY = "ctrl+cmd+v"
DEFAULT_POLL_INTERVAL = 0.25
CONFIG_PATH = Path.home() / ".config" / "clipmgr" / "config.toml"

# Carbon modifier masks (Events.h)
CMD = 0x0100
SHIFT = 0x0200
OPTION = 0x0800
CTRL = 0x1000

MODIFIERS = {
    "cmd": CMD, "command": CMD, "⌘": CMD,
    "shift": SHIFT, "⇧": SHIFT,
    "opt": OPTION, "option": OPTION, "alt": OPTION, "⌥": OPTION,
    "ctrl": CTRL, "control": CTRL, "⌃": CTRL,
}

# macOS virtual key codes for an ANSI keyboard (HIToolbox/Events.h, kVK_*)
KEY_CODES = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04, "g": 0x05,
    "z": 0x06, "x": 0x07, "c": 0x08, "v": 0x09, "b": 0x0B, "q": 0x0C,
    "w": 0x0D, "e": 0x0E, "r": 0x0F, "y": 0x10, "t": 0x11, "1": 0x12,
    "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17, "=": 0x18,
    "9": 0x19, "7": 0x1A, "-": 0x1B, "8": 0x1C, "0": 0x1D, "]": 0x1E,
    "o": 0x1F, "u": 0x20, "[": 0x21, "i": 0x22, "p": 0x23, "l": 0x25,
    "j": 0x26, "'": 0x27, "k": 0x28, ";": 0x29, "\\": 0x2A, ",": 0x2B,
    "/": 0x2C, "n": 0x2D, "m": 0x2E, ".": 0x2F, "`": 0x32,
    "space": 0x31,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60, "f6": 0x61,
    "f7": 0x62, "f8": 0x64, "f9": 0x65, "f10": 0x6D, "f11": 0x67, "f12": 0x6F,
    "f13": 0x69, "f14": 0x6B, "f15": 0x71, "f16": 0x6A, "f17": 0x40,
    "f18": 0x4F, "f19": 0x50, "f20": 0x5A,
}

_KEY_SYMBOLS = {"space": "Space"}
_MOD_SYMBOLS = [(CTRL, "⌃"), (OPTION, "⌥"), (SHIFT, "⇧"), (CMD, "⌘")]


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Hotkey:
    key: str
    key_code: int
    modifiers: int

    @property
    def display(self) -> str:
        mods = "".join(sym for mask, sym in _MOD_SYMBOLS if self.modifiers & mask)
        return mods + _KEY_SYMBOLS.get(self.key, self.key.upper())


@dataclass(frozen=True)
class Config:
    hotkey: Hotkey
    poll_interval: float


def parse_hotkey(spec: str) -> Hotkey:
    """Parse e.g. ``"ctrl+cmd+v"`` into a key code and Carbon modifier mask."""
    parts = [p.strip().lower() for p in spec.split("+")]
    if not parts or any(not p for p in parts):
        raise ConfigError(f"Invalid hotkey {spec!r}")
    *mod_names, key = parts
    modifiers = 0
    for name in mod_names:
        if name not in MODIFIERS:
            raise ConfigError(f"Unknown modifier {name!r} in hotkey {spec!r}")
        modifiers |= MODIFIERS[name]
    if key not in KEY_CODES:
        raise ConfigError(f"Unknown key {key!r} in hotkey {spec!r}")
    is_function_key = key.startswith("f") and key[1:].isdigit()
    if not is_function_key and not modifiers & (CMD | CTRL):
        # A plain key would hijack normal typing, and macOS 15+ refuses to
        # register hotkeys whose only modifiers are Option / Option+Shift.
        raise ConfigError(
            f"Hotkey {spec!r} must include cmd or ctrl (macOS rejects "
            "option-only and option+shift-only hotkeys)"
        )
    return Hotkey(key, KEY_CODES[key], modifiers)


def load_config(path: Path | None = None) -> Config:
    """Load settings, falling back to defaults when the file is missing."""
    path = CONFIG_PATH if path is None else path
    data: dict = {}
    if path.exists():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{path}: {exc}") from exc
    hotkey = parse_hotkey(str(data.get("hotkey", DEFAULT_HOTKEY)))
    try:
        poll_interval = float(data.get("poll_interval", DEFAULT_POLL_INTERVAL))
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{path}: poll_interval must be a number") from exc
    if not 0.05 <= poll_interval <= 2.0:
        raise ConfigError(f"{path}: poll_interval must be between 0.05 and 2.0")
    return Config(hotkey=hotkey, poll_interval=poll_interval)
