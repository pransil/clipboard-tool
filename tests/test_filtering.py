from clipmgr.filtering import (
    CONCEALED_TYPE,
    TRANSIENT_TYPE,
    is_sensitive,
    should_record,
)

STRING = "public.utf8-plain-text"


def test_plain_text_recorded():
    assert should_record([STRING], "hello") is True


def test_concealed_skipped():
    assert should_record([STRING, CONCEALED_TYPE], "hunter2") is False


def test_transient_skipped():
    assert should_record([TRANSIENT_TYPE, STRING], "one-time code") is False


def test_both_markers_skipped():
    assert should_record([CONCEALED_TYPE, TRANSIENT_TYPE, STRING], "pw") is False


def test_marker_alone_is_sensitive():
    assert is_sensitive([CONCEALED_TYPE]) is True
    assert is_sensitive([STRING]) is False
    assert is_sensitive(None) is False


def test_missing_or_empty_text_skipped():
    assert should_record([STRING], None) is False
    assert should_record([STRING], "") is False
    assert should_record([STRING], "   ") is False


def test_non_text_only_skipped():
    # e.g. an image copy: there is no string representation
    assert should_record(["public.png"], None) is False


def test_objc_like_type_objects_are_compared_as_strings():
    class FakeNSString(str):
        pass

    assert should_record([FakeNSString(CONCEALED_TYPE)], "pw") is False
