# clipmgr

A small macOS clipboard history manager. Keep using ⌘C / ⌘V as usual. When you
need something you copied earlier, press **⌃⌘V** and pick it from a list.

- Text only. The last **10** copies, plus any number of **pinned** items.
- Lives in the menu bar (no Dock icon).
- History is kept **in memory only**. Nothing is written to disk, and quitting clears it.
- Copies that password managers mark as concealed or transient
  (`org.nspasteboard.ConcealedType` / `TransientType`) are never recorded.

## Run

Requires macOS and [uv](https://docs.astral.sh/uv/).

```sh
uv run python -m clipmgr     # or: uv run clipmgr
```

Quit from the menu bar icon (**Quit clipmgr**) or with Ctrl+C in the terminal.

### Permissions

| What | Permission | Why |
|---|---|---|
| ⌃⌘V hotkey | none | Uses Carbon `RegisterEventHotKey`, which needs no permission |
| Watching the clipboard | none | |
| Pasting into the app you were using | **Accessibility** | clipmgr sends ⌘V for you |

On first launch clipmgr explains this and offers to open
**System Settings → Privacy & Security → Accessibility**. When you run it from a
terminal, macOS lists the *terminal app* (Terminal, iTerm, VS Code…). Turn that
one on, then restart clipmgr. Input Monitoring is not needed.

Without Accessibility, picking an item still copies it, and the menu bar
shows "Copied — press ⌘V".

## Use

Press **⌃⌘V** (or click the menu bar icon → Show Clipboard History).

| Key | Action |
|---|---|
| `1`…`9`, `0` | paste recent item 1…10 (1 = most recent copy) |
| `a`…`z` | paste a pinned item |
| ↑ ↓, then ⏎ | move, then paste the highlighted item |
| click | paste that item |
| ⌘P | pin / unpin the highlighted item |
| ⌫ | delete the highlighted item |
| esc, or ⌃⌘V again | close |
| right-click | Paste / Pin / Delete menu |

- **Clear history** removes unpinned items. **Clear everything** also removes pins.
  Both are in the popup and the menu bar menu.
- Picking an item moves it to the top of the recent list. Pinned items keep their place.
- Copying something already in the list moves it to the top instead of adding a duplicate.
- Pinned items don't count toward the 10-item limit and stay until you unpin or delete them.

## Configure

Optional: `~/.config/clipmgr/config.toml`

```toml
hotkey = "ctrl+cmd+v"   # e.g. "cmd+shift+v", "ctrl+option+space", "f13"
poll_interval = 0.25    # seconds between clipboard checks (0.05–2.0)
```

Modifiers: `cmd`, `ctrl`, `option`/`alt`, `shift`. A hotkey must include `cmd` or `ctrl`
(F-keys excepted), because macOS rejects option-only shortcuts. This file holds
settings only, never clipboard contents.

## Develop

```text
src/clipmgr/
  history.py    filtering.py    watcher.py    config.py    display.py   # pure Python, unit-tested
  macos/        pasteboard.py   hotkey.py     paste.py     popup.py     app.py
tests/          unit tests for the pure modules (run anywhere)
scripts/        copy_sensitive.py: manual test helper
```

```sh
uv run pytest
```

### Manual test checklist (macOS)

1. Copy 12 distinct lines in TextEdit, then press ⌃⌘V. Expect exactly 10 recent items, numbered 1–0.
   Pin one (⌘P), copy 12 more lines, and check that the pin is still there as `a`.
2. In TextEdit, press ⌃⌘V then `3`. The third item is pasted at the cursor and shows as `1` next time.
   Repeat with ↑↓ + ⏎, with a click, and with a letter for a pinned item.
3. Check ⌘P (unpin), ⌫ (delete), **Clear history** (pins remain), and **Clear everything** (empty).
4. Run `uv run python scripts/copy_sensitive.py`, then open the popup. The text must not appear.
   Repeat with `--transient`. Then copy a password from Passwords or 1Password, if one is installed.
5. Turn Accessibility off. Picking an item copies it and shows "press ⌘V". Turn it back on,
   restart clipmgr, and check that auto-paste works.
6. Gmail (user-supervised): paste into a draft from the popup. Check the text, **do not send**,
   then discard the draft.
7. Quit and relaunch. The history is empty.

## Known limitations (v1)

- Plain text only (no images, files, RTF/HTML). No sync, no persistence.
- Auto-paste sends the physical V key (ANSI key code 9). Non-QWERTY layouts such as Dvorak
  may paste the wrong shortcut.
- Running from a terminal ties the Accessibility permission to that terminal app.

## Phase 2 ideas

- Credential queue: copy a username and password, then paste them in order. Both are held
  in memory only and cleared after use or after 30–60 s. Never pinned, never in history.
- A `.app` bundle (py2app) with its own permission entry and an optional login item.
