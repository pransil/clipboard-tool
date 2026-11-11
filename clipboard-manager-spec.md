# Clipboard Manager: Build Spec

## Context
- Platform: macOS 26.6.2 (Apple silicon or Intel, to confirm)
- Language: Python (user codes primarily in Python)
- Scope for v1: text only
- The user keeps using normal Cmd+C / Cmd+V. The manager adds a history popup for when a list is needed.

## Goals (in priority order)
1. Simple to use
2. Popup listing the last 10 text items, numbered 1 to 10
3. Easy selection: press a number, or use arrow keys and Enter, or click
4. Pins: pinned items stay until the user unpins or deletes them
5. Clear: one action clears unpinned history, a second clears everything

## Functional requirements
- Store the last 10 unpinned text items in memory, plus any number of pinned items.
- Global hotkey (choose a default, e.g. Cmd+Shift+V, and make it configurable) opens the popup.
- Pressing a number pastes that item into the frontmost app and closes the popup.
- Selecting an item moves it to the top of history. Duplicate consecutive copies are ignored.
- Pin/unpin from the popup. Pinned items are shown at the top.
- "Clear history" and "Clear everything" actions.
- Clipboard watching: check `NSPasteboard.generalPasteboard().changeCount` several times per second (macOS has no clipboard-change event).

## Security requirements
- Skip any copy marked with `org.nspasteboard.ConcealedType` or `org.nspasteboard.TransientType`. These are passwords and similar values from password managers.
- Do not write history to disk in v1. Keep everything in memory, cleared on quit.
- Credential queue (optional, phase 2): user copies a username and password, then pastes them in order. Both values are held in memory only and cleared after 30 to 60 seconds or after use. Never pinned, never in history.

## Explicitly out of scope for v1
- Images, files, and RTF/HTML formats. Store plain text only.
- Syncing across devices.
- Persistent history on disk.

## Suggested implementation
- PyObjC for `NSPasteboard`, and for a floating window if the popup needs more than a menu.
- A menu bar app (e.g. `rumps`, or PyObjC `NSStatusItem`) as the entry point.
- Global hotkey via a library such as `pynput`, or a Carbon/AppKit hotkey API. Note that macOS needs Accessibility and Input Monitoring permissions for this, and the app should explain that on first run.
- Keep the history logic (add, dedupe, pin, unpin, clear, cap at 10) in plain Python with no macOS dependencies, so it can be unit-tested anywhere.

## Testing plan
1. Unit tests for history logic: cap at 10, dedupe, pin survives cap, clear behavior, selection reorders history.
2. Unit tests for concealed/transient filtering, using fake pasteboard data.
3. Manual test on macOS:
   - Copy 12 items, confirm only 10 unpinned remain and pinned items persist.
   - Open the popup with the hotkey, select a number, confirm the right text is pasted.
   - Copy a password from a password manager, confirm it does not appear in the popup.
4. Gmail test (manual, user-supervised): paste text into a draft. Do NOT send email. Confirm the draft is discarded afterward.

## Open questions for the user
- Hotkey preference, if any.
- Menu bar app is acceptable (assumed yes unless stated otherwise).
- Keep credential queue in v1 or phase 2?
