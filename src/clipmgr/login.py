"""Login helper: hold a username and password briefly and paste them in order.

Pure Python, no macOS dependencies.

    IDLE ──start──▶ CAPTURE_USERNAME ──copy──▶ CAPTURE_PASSWORD ──copy──▶ READY
      ▲                                                                    │
      └──────── both pasted · cancel · timeout (wipes both values) ◀───────┘

The values live only in this object. They never go into History, are never
pinned, and are dropped when both have been pasted, on cancel, or after
``timeout`` seconds without activity.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import Enum

USERNAME = "username"
PASSWORD = "password"
FIELDS = (USERNAME, PASSWORD)
LABELS = {USERNAME: "Username", PASSWORD: "Password"}

MASK = "•"
PASSWORD_MASK = MASK * 8  # fixed length, so the real length is never shown
DEFAULT_TIMEOUT = 60.0


class Phase(Enum):
    IDLE = "idle"
    CAPTURE_USERNAME = "capture_username"
    CAPTURE_PASSWORD = "capture_password"
    READY = "ready"


def clean(field: str, text: str | None) -> str | None:
    """Normalize a copied value. Returns None if it is unusable.

    Usernames lose surrounding whitespace. Passwords only lose trailing line
    breaks (copying a line from a note often includes one, and pasting it would
    submit the form); other spaces may be part of the password.
    """
    if text is None:
        return None
    value = text.strip() if field == USERNAME else text.rstrip("\r\n")
    return value or None


def mask(field: str, value: str) -> str:
    """Display form: first two characters of a username, nothing of a password."""
    if field == PASSWORD or len(value) < 4:
        return PASSWORD_MASK
    return value[:2] + MASK * 6


class LoginSession:
    def __init__(
        self, timeout: float = DEFAULT_TIMEOUT, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.timeout = timeout
        self._clock = clock
        self._values: dict[str, str] = {}
        self._pasted: set[str] = set()
        self._deadline = 0.0
        self.phase = Phase.IDLE

    # ----- state -----------------------------------------------------------

    @property
    def active(self) -> bool:
        return self.phase is not Phase.IDLE

    @property
    def capturing(self) -> bool:
        return self.phase in (Phase.CAPTURE_USERNAME, Phase.CAPTURE_PASSWORD)

    @property
    def ready(self) -> bool:
        return self.phase is Phase.READY

    def has(self, field: str) -> bool:
        return field in self._values

    def is_pasted(self, field: str) -> bool:
        return field in self._pasted

    def masked(self, field: str) -> str:
        value = self._values.get(field)
        return mask(field, value) if value is not None else ""

    def next_field(self) -> str | None:
        """The field the next "paste" will use, once ready."""
        if not self.ready:
            return None
        return next((f for f in FIELDS if f not in self._pasted), None)

    def remaining(self) -> float:
        if not self.active:
            return 0.0
        return max(0.0, self._deadline - self._clock())

    # ----- transitions -------------------------------------------------------

    def start(self) -> None:
        self._wipe()
        self.phase = Phase.CAPTURE_USERNAME
        self.touch()

    def cancel(self) -> None:
        self._wipe()

    def touch(self) -> None:
        """Restart the inactivity timeout."""
        self._deadline = self._clock() + self.timeout

    def expire_if_due(self) -> bool:
        """Wipe the session if it timed out. Returns True if it did."""
        if self.active and self._clock() >= self._deadline:
            self._wipe()
            return True
        return False

    def capture(self, text: str | None) -> str | None:
        """Record a value copied during capture. Returns the field filled, or None.

        A second copy identical to the username (e.g. "copy username" pressed
        twice) is ignored rather than taken as the password.
        """
        if self.phase is Phase.CAPTURE_USERNAME:
            field = USERNAME
        elif self.phase is Phase.CAPTURE_PASSWORD:
            field = PASSWORD
        else:
            return None
        value = clean(field, text)
        if value is None:
            return None
        if field == PASSWORD and value == self._values.get(USERNAME):
            return None
        self._values[field] = value
        self.phase = Phase.CAPTURE_PASSWORD if field == USERNAME else Phase.READY
        self.touch()
        return field

    def take(self, field: str | None = None) -> tuple[str, str, bool]:
        """Hand out a value to paste: ``(field, value, finished)``.

        ``field=None`` means the next one in order (username, then password).
        Once both have been pasted the session is wiped and ``finished`` is True.
        """
        if not self.ready:
            raise RuntimeError("login helper is not ready to paste")
        field = field or self.next_field()
        if field not in self._values:
            raise KeyError(field)
        value = self._values[field]
        self._pasted.add(field)
        finished = all(f in self._pasted for f in FIELDS)
        if finished:
            self._wipe()
        else:
            self.touch()
        return field, value, finished

    def swap(self) -> None:
        """Exchange username and password (copied in the wrong order)."""
        if not self.ready:
            return
        self._values[USERNAME], self._values[PASSWORD] = (
            self._values[PASSWORD],
            self._values[USERNAME],
        )
        self._pasted.clear()
        self.touch()

    def _wipe(self) -> None:
        self._values.clear()
        self._pasted.clear()
        self._deadline = 0.0
        self.phase = Phase.IDLE
