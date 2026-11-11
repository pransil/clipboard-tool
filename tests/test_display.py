from clipmgr.display import (
    build_rows,
    default_selection,
    item_for_key,
    next_selectable,
    preview,
    row_for_item,
    tooltip,
)
from clipmgr.history import History


def make(recent=(), pinned=()):
    h = History()
    for t in pinned:
        h.add(t)
        h.pin(h.recent[0].id)
    for t in recent:
        h.add(t)
    return h


def test_recent_keys_1_to_0():
    h = make(recent=[f"t{i}" for i in range(1, 11)])  # newest is t10
    rows = build_rows(h)
    assert [r.key for r in rows] == list("1234567890")
    assert item_for_key("1", h).text == "t10"
    assert item_for_key("0", h).text == "t1"


def test_pinned_keys_letters_and_headers():
    h = make(recent=["r1"], pinned=["p1", "p2"])
    rows = build_rows(h)
    assert [(r.kind, r.key) for r in rows] == [
        ("header", ""),
        ("item", "a"),
        ("item", "b"),
        ("header", ""),
        ("item", "1"),
    ]
    assert item_for_key("a", h).text == "p1"
    assert item_for_key("B", h).text == "p2"
    assert item_for_key("1", h).text == "r1"


def test_no_headers_without_pins():
    rows = build_rows(make(recent=["x"]))
    assert [r.kind for r in rows] == ["item"]


def test_keys_beyond_contents_return_none():
    h = make(recent=["x"], pinned=["p"])
    assert item_for_key("2", h) is None
    assert item_for_key("c", h) is None
    assert item_for_key("-", h) is None
    assert item_for_key("", h) is None


def test_empty_state():
    rows = build_rows(History())
    assert [r.kind for r in rows] == ["empty"]
    assert default_selection(rows) is None


def test_default_selection_prefers_recent_one():
    h = make(recent=["r1", "r2"], pinned=["p1"])
    rows = build_rows(h)
    assert rows[default_selection(rows)].item.text == "r2"  # newest recent


def test_default_selection_falls_back_to_pin():
    rows = build_rows(make(pinned=["p1"]))
    assert rows[default_selection(rows)].item.text == "p1"


def test_next_selectable_skips_headers():
    h = make(recent=["r1"], pinned=["p1"])
    rows = build_rows(h)  # header, p1, header, r1
    assert next_selectable(rows, 1, +1) == 3
    assert next_selectable(rows, 3, -1) == 1
    assert next_selectable(rows, 1, -1) is None
    assert next_selectable(rows, 3, +1) is None


def test_row_for_item():
    h = make(recent=["r1"], pinned=["p1"])
    rows = build_rows(h)
    assert row_for_item(rows, h.recent[0].id) == 3
    assert row_for_item(rows, 999) is None


def test_preview_collapses_whitespace_and_marks_newlines():
    assert preview("def foo(bar):\n    return  1\n") == "def foo(bar): ⏎ return 1"
    assert preview("a\n\n\nb") == "a ⏎ b"


def test_preview_truncates():
    p = preview("x" * 200, limit=20)
    assert len(p) == 20
    assert p.endswith("…")


def test_preview_whitespace_only():
    assert preview(" \n ") == "(whitespace)"


def test_tooltip_truncates_long_text():
    assert tooltip("short") == "short"
    long = tooltip("y" * 1000, limit=10)
    assert long.startswith("y" * 10 + "…")
    assert "1,000 characters" in long
