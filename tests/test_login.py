import pytest

from clipmgr.login import (
    PASSWORD,
    PASSWORD_MASK,
    USERNAME,
    LoginSession,
    Phase,
    clean,
    mask,
)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def ready_session(clock=None, username="alex@example.com", password="s3cret pw"):
    s = LoginSession(timeout=60, clock=clock or FakeClock())
    s.start()
    s.capture(username)
    s.capture(password)
    return s


def test_starts_idle():
    s = LoginSession()
    assert s.phase is Phase.IDLE
    assert not s.active
    assert s.capture("x") is None  # copies are not captured unless started
    assert s.next_field() is None


def test_capture_username_then_password():
    s = LoginSession(clock=FakeClock())
    s.start()
    assert s.phase is Phase.CAPTURE_USERNAME
    assert s.capture("alex@example.com") == USERNAME
    assert s.phase is Phase.CAPTURE_PASSWORD
    assert s.capture("hunter2") == PASSWORD
    assert s.phase is Phase.READY
    assert s.next_field() == USERNAME


def test_paste_in_order_then_wiped():
    s = ready_session()
    assert s.take() == (USERNAME, "alex@example.com", False)
    assert s.next_field() == PASSWORD
    assert s.take() == (PASSWORD, "s3cret pw", True)
    assert s.phase is Phase.IDLE
    assert not s.has(USERNAME) and not s.has(PASSWORD)


def test_click_specific_field_and_repaste():
    s = ready_session()
    assert s.take(PASSWORD)[:2] == (PASSWORD, "s3cret pw")
    assert s.active  # username still unpasted
    assert s.next_field() == USERNAME
    assert s.take(PASSWORD)[2] is False  # pasting the same field again is allowed
    assert s.take(USERNAME)[2] is True


def test_take_before_ready_raises():
    s = LoginSession()
    s.start()
    with pytest.raises(RuntimeError):
        s.take()


def test_cancel_wipes_everything():
    s = ready_session()
    s.cancel()
    assert s.phase is Phase.IDLE
    assert s.masked(USERNAME) == "" and s.masked(PASSWORD) == ""


def test_restart_discards_previous_values():
    s = ready_session()
    s.start()
    assert s.phase is Phase.CAPTURE_USERNAME
    assert not s.has(USERNAME)


def test_timeout_after_inactivity():
    clock = FakeClock()
    s = LoginSession(timeout=60, clock=clock)
    s.start()
    clock.now += 59
    assert s.expire_if_due() is False
    assert s.remaining() == pytest.approx(1)
    clock.now += 2
    assert s.expire_if_due() is True
    assert s.phase is Phase.IDLE
    assert s.remaining() == 0


def test_activity_resets_timeout():
    clock = FakeClock()
    s = LoginSession(timeout=60, clock=clock)
    s.start()
    clock.now += 50
    s.capture("alex")
    clock.now += 50
    assert s.expire_if_due() is False  # 50 s since the last copy
    s.capture("pw")
    clock.now += 50
    s.take()
    clock.now += 59
    assert s.expire_if_due() is False
    clock.now += 2
    assert s.expire_if_due() is True


def test_empty_and_whitespace_copies_ignored():
    s = LoginSession(clock=FakeClock())
    s.start()
    assert s.capture("   ") is None
    assert s.capture("") is None
    assert s.phase is Phase.CAPTURE_USERNAME


def test_duplicate_username_copy_not_taken_as_password():
    s = LoginSession(clock=FakeClock())
    s.start()
    s.capture("alex")
    assert s.capture("alex") is None
    assert s.phase is Phase.CAPTURE_PASSWORD


def test_swap():
    s = ready_session()
    s.swap()
    assert s.take()[:2] == (USERNAME, "s3cret pw")
    assert s.take()[:2] == (PASSWORD, "alex@example.com")


def test_swap_ignored_unless_ready():
    s = LoginSession(clock=FakeClock())
    s.start()
    s.capture("alex")
    s.swap()
    assert s.phase is Phase.CAPTURE_PASSWORD


def test_clean_rules():
    assert clean(USERNAME, "  alex@example.com \n") == "alex@example.com"
    assert clean(PASSWORD, " pass word \n") == " pass word "
    assert clean(PASSWORD, "pw\r\n") == "pw"
    assert clean(PASSWORD, "\n") is None
    assert clean(USERNAME, None) is None


def test_masking_never_reveals_password():
    assert mask(PASSWORD, "x") == PASSWORD_MASK
    assert mask(PASSWORD, "a much longer password") == PASSWORD_MASK
    assert mask(USERNAME, "alex@example.com") == "al••••••"
    assert mask(USERNAME, "abc") == PASSWORD_MASK  # too short to show a prefix
    s = ready_session()
    assert s.masked(PASSWORD) == PASSWORD_MASK
    assert "s3cret" not in s.masked(PASSWORD)
