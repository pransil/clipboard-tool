from clipmgr.filtering import CONCEALED_TYPE, TRANSIENT_TYPE
from clipmgr.history import History
from clipmgr.watcher import ClipboardWatcher, Snapshot

STRING = "public.utf8-plain-text"


class FakePasteboard:
    """Mimics NSPasteboard: every write bumps the change count."""

    def __init__(self):
        self.change_count = 0
        self.snapshot = Snapshot((), None)
        self.snapshot_reads = 0

    def copy(self, text, *extra_types):
        self.change_count += 1
        self.snapshot = Snapshot((STRING, *extra_types), text)
        return self.change_count

    def read_change_count(self):
        return self.change_count

    def read_snapshot(self):
        self.snapshot_reads += 1
        return self.snapshot


def make():
    pb = FakePasteboard()
    history = History()
    watcher = ClipboardWatcher(pb.read_change_count, pb.read_snapshot, history)
    return pb, history, watcher


def recent_texts(history):
    return [item.text for item in history.recent]


def test_unchanged_count_does_not_read_contents():
    pb, history, watcher = make()
    pb.copy("A")
    watcher.poll()
    reads = pb.snapshot_reads
    for _ in range(5):
        assert watcher.poll() is False
    assert pb.snapshot_reads == reads


def test_changed_count_records_item():
    pb, history, watcher = make()
    pb.copy("A")
    assert watcher.poll() is True
    pb.copy("B")
    assert watcher.poll() is True
    assert recent_texts(history) == ["B", "A"]


def test_existing_clipboard_captured_on_first_poll():
    pb, history, watcher = make()
    pb.copy("already there")
    watcher.poll()
    assert recent_texts(history) == ["already there"]


def test_concealed_copy_not_recorded():
    pb, history, watcher = make()
    pb.copy("hunter2", CONCEALED_TYPE)
    assert watcher.poll() is False
    pb.copy("123456", TRANSIENT_TYPE)
    assert watcher.poll() is False
    assert recent_texts(history) == []


def test_sensitive_copy_between_normal_copies():
    pb, history, watcher = make()
    pb.copy("user@example.com")
    watcher.poll()
    pb.copy("s3cret", CONCEALED_TYPE)
    watcher.poll()
    pb.copy("next")
    watcher.poll()
    assert recent_texts(history) == ["next", "user@example.com"]


def test_own_write_is_ignored():
    pb, history, watcher = make()
    pb.copy("A")
    watcher.poll()
    own = pb.copy("written by app")
    watcher.ignore(own)
    assert watcher.poll() is False
    assert recent_texts(history) == ["A"]
    # Later user copies are still recorded.
    pb.copy("C")
    assert watcher.poll() is True


def test_stale_ignored_count_is_dropped():
    pb, history, watcher = make()
    watcher.ignore(1)
    pb.copy("A")
    pb.copy("B")  # count jumps to 2 before the poll; 1 was never seen
    assert watcher.poll() is True
    assert recent_texts(history) == ["B"]
    assert watcher._ignored == set()


def test_many_copies_between_polls_records_latest():
    pb, history, watcher = make()
    pb.copy("A")
    pb.copy("B")
    pb.copy("C")
    watcher.poll()
    assert recent_texts(history) == ["C"]
