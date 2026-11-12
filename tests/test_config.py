import pytest

from clipmgr.config import (
    CMD,
    CTRL,
    DEFAULT_POLL_INTERVAL,
    OPTION,
    SHIFT,
    DEFAULT_HOTKEY,
    ConfigError,
    load_config,
    parse_hotkey,
)


def test_default_hotkey_is_option_cmd_v():
    hk = parse_hotkey(DEFAULT_HOTKEY)
    assert (hk.key_code, hk.modifiers) == (9, CMD | OPTION)
    assert hk.display == "⌥⌘V"


def test_ctrl_cmd_v():
    hk = parse_hotkey("ctrl+cmd+v")
    assert (hk.key_code, hk.modifiers) == (9, 0x1100)
    assert hk.display == "⌃⌘V"


def test_modifier_aliases_and_case():
    hk = parse_hotkey("Command + Shift + V")
    assert (hk.key_code, hk.modifiers) == (9, CMD | SHIFT)
    assert hk.display == "⇧⌘V"


def test_option_with_cmd_allowed():
    hk = parse_hotkey("cmd+option+v")
    assert hk.modifiers == CMD | OPTION


def test_function_key_without_modifiers_allowed():
    hk = parse_hotkey("f13")
    assert (hk.key_code, hk.modifiers) == (0x69, 0)


@pytest.mark.parametrize("spec", ["option+v", "option+shift+v", "shift+v", "v"])
def test_rejects_hotkeys_without_cmd_or_ctrl(spec):
    with pytest.raises(ConfigError):
        parse_hotkey(spec)


@pytest.mark.parametrize("spec", ["ctrl+cmd+", "ctrl+cmd+enterr", "hyper+v", ""])
def test_rejects_unknown_parts(spec):
    with pytest.raises(ConfigError):
        parse_hotkey(spec)


def test_missing_file_uses_defaults(tmp_path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.hotkey.display == "⌥⌘V"
    assert cfg.poll_interval == DEFAULT_POLL_INTERVAL


def test_file_overrides(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('hotkey = "cmd+shift+v"\npoll_interval = 0.5\n')
    cfg = load_config(path)
    assert cfg.hotkey.modifiers == CMD | SHIFT
    assert cfg.poll_interval == 0.5


def test_bad_toml_raises(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("hotkey = ")
    with pytest.raises(ConfigError):
        load_config(path)


def test_bad_poll_interval_raises(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("poll_interval = 10\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_ctrl_alone_is_enough():
    assert parse_hotkey("ctrl+v").modifiers == CTRL


def test_login_defaults(tmp_path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.login_hotkey.display == "⌃⌘L"
    assert cfg.login_timeout == 60


def test_login_overrides(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('login_hotkey = "ctrl+option+cmd+l"\nlogin_timeout = 30\n')
    cfg = load_config(path)
    assert cfg.login_hotkey.modifiers == CTRL | OPTION | CMD
    assert cfg.login_timeout == 30


@pytest.mark.parametrize("value", ["5", "1000", '"soon"'])
def test_bad_login_timeout_raises(tmp_path, value):
    path = tmp_path / "config.toml"
    path.write_text(f"login_timeout = {value}\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_login_hotkey_must_differ(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('hotkey = "ctrl+cmd+l"\n')
    with pytest.raises(ConfigError):
        load_config(path)
