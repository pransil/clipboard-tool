import pytest

from clipmgr.history import History


def texts(items):
    return [item.text for item in items]


def fill(history, n, prefix="item"):
    for i in range(1, n + 1):
        history.add(f"{prefix}{i}")


def test_caps_at_ten_and_drops_oldest():
    h = History()
    fill(h, 12)
    assert len(h.recent) == 10
    assert texts(h.recent) == [f"item{i}" for i in range(12, 2, -1)]


def test_consecutive_duplicate_ignored():
    h = History()
    assert h.add("A") is True
    assert h.add("A") is False
    assert texts(h.recent) == ["A"]


def test_non_consecutive_duplicate_moves_to_top():
    h = History()
    for t in ["A", "B", "A"]:
        h.add(t)
    assert texts(h.recent) == ["A", "B"]


def test_empty_and_whitespace_ignored():
    h = History()
    assert h.add("") is False
    assert h.add(None) is False
    assert h.add("  \n\t ") is False
    assert len(h) == 0


def test_whitespace_preserved_in_text():
    h = History()
    h.add("  indented\n")
    assert texts(h.recent) == ["  indented\n"]


def test_pin_survives_cap():
    h = History()
    h.add("keep me")
    h.pin(h.recent[0].id)
    fill(h, 12)
    assert texts(h.pinned) == ["keep me"]
    assert len(h.recent) == 10
    assert all(item.pinned for item in h.pinned)


def test_any_number_of_pins():
    h = History()
    fill(h, 10)
    for item in list(h.recent):
        h.pin(item.id)
    fill(h, 10, prefix="new")
    assert len(h.pinned) == 10
    assert len(h.recent) == 10


def test_copying_pinned_text_does_not_duplicate():
    h = History()
    h.add("X")
    h.pin(h.recent[0].id)
    assert h.add("X") is False
    assert texts(h.recent) == []
    assert texts(h.pinned) == ["X"]


def test_clear_history_keeps_pins():
    h = History()
    fill(h, 5)
    h.pin(h.recent[2].id)
    h.clear_history()
    assert texts(h.recent) == []
    assert texts(h.pinned) == ["item3"]


def test_clear_all_removes_everything():
    h = History()
    fill(h, 5)
    h.pin(h.recent[0].id)
    h.clear_all()
    assert len(h) == 0


def test_select_moves_recent_item_to_top():
    h = History()
    fill(h, 5)  # recent: item5, item4, item3, item2, item1
    third = h.recent[2]
    assert h.select(third.id) == "item3"
    assert texts(h.recent) == ["item3", "item5", "item4", "item2", "item1"]


def test_select_pinned_keeps_order():
    h = History()
    fill(h, 3)
    for item in list(h.recent):
        h.pin(item.id)  # pinned in order: item3, item2, item1
    before = texts(h.pinned)
    assert h.select(h.pinned[2].id) == "item1"
    assert texts(h.pinned) == before
    assert texts(h.recent) == []


def test_pin_and_unpin_move_between_sections():
    h = History()
    fill(h, 3)
    target = h.recent[1]  # item2
    h.pin(target.id)
    assert texts(h.pinned) == ["item2"]
    assert texts(h.recent) == ["item3", "item1"]
    h.unpin(target.id)
    assert texts(h.pinned) == []
    assert texts(h.recent) == ["item2", "item3", "item1"]
    assert not h.recent[0].pinned


def test_unpin_applies_cap():
    h = History()
    h.add("pinned")
    pinned_id = h.recent[0].id
    h.pin(pinned_id)
    fill(h, 10)
    h.unpin(pinned_id)
    assert len(h.recent) == 10
    assert h.recent[0].text == "pinned"
    assert "item1" not in texts(h.recent)


def test_toggle_pin():
    h = History()
    h.add("A")
    item_id = h.recent[0].id
    h.toggle_pin(item_id)
    assert texts(h.pinned) == ["A"]
    h.toggle_pin(item_id)
    assert texts(h.recent) == ["A"]


def test_delete_recent_and_pinned():
    h = History()
    fill(h, 3)
    h.pin(h.recent[0].id)  # pin item3
    h.delete(h.pinned[0].id)
    h.delete(h.recent[0].id)  # item2
    assert texts(h.pinned) == []
    assert texts(h.recent) == ["item1"]


def test_unknown_id_raises():
    h = History()
    for op in (h.select, h.pin, h.unpin, h.delete):
        with pytest.raises(KeyError):
            op(999)


def test_ids_are_stable_across_moves():
    h = History()
    fill(h, 3)
    ids = {item.text: item.id for item in h.recent}
    h.add("item1")  # move to top
    h.pin(ids["item2"])
    assert h.get(ids["item1"]).text == "item1"
    assert h.get(ids["item2"]).pinned
