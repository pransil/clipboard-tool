# clipmgr

A small macOS clipboard history manager. Keep using ⌘C / ⌘V as usual. When you
need something you copied earlier, press **⌥⌘V** in any app and pick it from a list.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/screenshot-dark.png">
    <img src="docs/screenshot-light.png" width="560" alt="The clipmgr popup: two pinned items labeled a and b above ten recent copies numbered 1 to 0, with Clear history and Clear everything buttons">
  </picture>
</p>

- Text only. The last **10** copies, plus any number of **pinned** items.
- Lives in the menu bar (no Dock icon).
- History is kept **in memory only**. Nothing is written to disk, and quitting clears it.
- Copies that password managers mark as concealed or transient
  (`org.nspasteboard.ConcealedType` / `TransientType`) are never recorded.
- A **login helper** (**⌃⌘L**) pastes a username and then a password into a login form,
  then forgets both.

## Setup (one time)

You need macOS and [uv](https://docs.astral.sh/uv/) (`brew install uv`).

### 1. Install

Put the project somewhere outside Desktop, Documents and Downloads. macOS
restricts those folders for apps that start at login.

```sh
git clone https://github.com/pransil/clipboard-tool.git ~/devel/clipboard-tool
cd ~/devel/clipboard-tool
uv sync
```

### 2. Start it at login

```sh
scripts/login-item.sh install
```

This starts clipmgr now and every time you log in or restart the Mac. A clipboard icon
appears in the menu bar. macOS may show a "Background Items Added" notification;
that's expected. The script installs a per-user LaunchAgent
(`~/Library/LaunchAgents/local.clipmgr.plist`). It relaunches clipmgr if it
crashes, but not after you choose **Quit**.

<details>
<summary>Prefer to run it by hand instead?</summary>

```sh
uv run python -m clipmgr     # Ctrl+C or menu bar → Quit to stop
```

Started this way, it runs until you quit it or log out. In step 3, macOS lists
your **terminal app** (Terminal, iTerm, VS Code…) instead of "Python".
</details>

### 3. Allow it to paste into other apps (Accessibility)

The shortcut and the history work right away with no permissions. To paste the item
you pick into the app you were using, clipmgr sends ⌘V for you, and macOS requires
the **Accessibility** permission for that.

1. On first start, clipmgr shows a dialog. Click **Open Accessibility Settings**.
   You can also go to **System Settings → Privacy & Security → Accessibility**.
2. Turn on **Python**. If you started clipmgr from a terminal, turn on your terminal app instead.
   Usually macOS adds the entry when clipmgr asks. If Python isn't listed, click **+**,
   press ⌘⇧G, and paste the path from the "Accessibility app" line of
   `scripts/login-item.sh status`.
3. Run `scripts/login-item.sh restart`.

Until you do this, picking an item still copies it, and the menu bar shows
"Copied — press ⌘V".

clipmgr does **not** need Input Monitoring or Screen Recording.

### 4. Check it works everywhere

The shortcut is system-wide, so it doesn't matter which app, window or browser tab is in front.
Check a few places:

- [ ] **TextEdit:** press ⌥⌘V, then `1`. Your last copy is pasted.
- [ ] **A browser tab** (a search box, a Google Doc, a Gmail draft): same test.
- [ ] **A full-screen app**, and **another desktop (Space)**: the popup appears on top.
- [ ] **A second display**, if you have one: the popup opens on the display with the mouse pointer.
- [ ] **After a restart:** the menu bar icon is back without running anything.

## Use

Press **⌥⌘V** (or click the menu bar icon → Show Clipboard History).

| Key | Action |
|---|---|
| `1`…`9`, `0` | paste recent item 1…10 (1 = most recent copy) |
| `a`…`z` | paste a pinned item |
| ↑ ↓, then ⏎ | move, then paste the highlighted item |
| click | paste that item |
| ⌘P | pin / unpin the highlighted item |
| ⌫ | delete the highlighted item |
| esc, or ⌥⌘V again | close |
| right-click | Paste / Pin / Delete menu |

- **Clear history** removes unpinned items. **Clear everything** also removes pins.
  Both are in the popup and the menu bar menu.
- Picking an item moves it to the top of the recent list. Pinned items keep their place.
- Copying something already in the list moves it to the top instead of adding a duplicate.
- ⌥⌘V is also Finder's *Move Item Here* shortcut for files. While clipmgr is running, use
  Finder's **Edit** menu instead: hold ⌥ and choose **Move Item Here**.
- Pinned items don't count toward the 10-item limit. They stay until you unpin or delete them,
  or quit clipmgr.

## Log in with the login helper

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/login-dark.png">
    <img src="docs/login-light.png" width="320" alt="The login helper panel: Username shown as al followed by dots and marked as next for Control-Command-L, Password shown as dots, with Swap and Clear buttons and a 1:00 countdown">
  </picture>
</p>

Use it when the username and password are somewhere else, such as a password manager, a note
or an email, and you'd otherwise switch back and forth to copy each one.

1. Press **⌃⌘L**. A small panel appears at the top right of the screen.
2. Copy the **username**, then the **password**, from wherever they are. The panel ticks each
   one off. These copies don't go into your history, and right after each one clipmgr puts
   your clipboard back to what it was before.
3. Click the login form's username field and press **⌃⌘L**. Press Tab (or *Next* on two-page
   logins), then press **⌃⌘L** again for the password. You can also click **Username** or
   **Password** in the panel. Clicking pastes without moving your cursor out of the form.

After the password is pasted, clipmgr wipes both values and closes the panel.

| If you… | Do this |
|---|---|
| copied them in the wrong order | **⇅ Swap** |
| changed your mind | **Cancel** / **Clear**, or press ⌃⌘L while it's still waiting for copies, or use menu bar → Cancel Login |
| walked away | Nothing. The values are wiped after 60 seconds without activity (see the countdown). |

How it keeps them safe:

- The values are held **in memory only**. They're never in the history or pins, and never on
  disk or in the log. Python can't guarantee the memory is overwritten, but clipmgr drops the
  values as soon as you're done.
- The password is never shown, not even its length. Only the first two characters of the
  username are shown.
- For the paste, each value sits on the clipboard for about a second. It's marked as concealed
  so other clipboard tools skip it, and kept off Universal Clipboard so it isn't sent to your
  other Apple devices.
- Without the Accessibility permission, ⌃⌘L puts the value on the clipboard and the panel
  says "press ⌘V". Your clipboard is restored 15 seconds later.

## Configure

Optional: `~/.config/clipmgr/config.toml`

```toml
hotkey = "cmd+option+v"      # history popup, e.g. "ctrl+cmd+v", "cmd+shift+v", "f13"
poll_interval = 0.25         # seconds between clipboard checks (0.05–2.0)
login_hotkey = "ctrl+cmd+l"  # login helper
login_timeout = 60           # seconds without activity before login values are wiped (10–300)
```

Modifiers: `cmd`, `ctrl`, `option`/`alt`, `shift`. A hotkey must include `cmd` or `ctrl`
(F-keys excepted), because macOS rejects option-only shortcuts. This file holds
settings only, never clipboard contents. Run `scripts/login-item.sh restart` after editing it.

## Troubleshooting

| Problem | Fix |
|---|---|
| Popup opens but nothing is pasted | Accessibility is off for the entry that started clipmgr ("Python" at login, or your terminal app). Turn it on, then `scripts/login-item.sh restart`. |
| Auto-paste stopped after `brew upgrade` | Homebrew installed a new Python build, and macOS treats it as a new app. In Accessibility, remove the old **Python** entry (−), then `scripts/login-item.sh restart` and allow it again. |
| ⌥⌘V does nothing | Check for the menu bar icon. If it's missing, run `scripts/login-item.sh status`. If clipmgr showed "Couldn't register the shortcut", another app owns ⌥⌘V; pick a different `hotkey` in the config file. |
| ⌥⌘V doesn't work in one particular app | That app may use ⌥⌘V itself, or it may have turned on secure keyboard entry (password fields, Terminal → Secure Keyboard Entry), which can block shortcuts and synthesized keys. |
| ⌃⌘L does nothing while a password field is selected | macOS turns on "secure input" in password fields, which can block shortcuts. Click **Password** in the login panel instead. |
| Two clipboard icons in the menu bar | One copy started at login and another from a terminal. Quit the terminal one. |
| Not starting at login | In **System Settings → General → Login Items & Extensions**, under *Allow in the Background*, make sure the Python entry (it may be listed as `python3.14`) is on. Then run `scripts/login-item.sh install` again. If you moved the project folder, reinstall too. |
| Logs | `~/Library/Logs/clipmgr.log` (start/stop and errors only, never clipboard contents) |

To stop starting at login: `scripts/login-item.sh uninstall`.

## Develop

```text
src/clipmgr/
  history.py  filtering.py  watcher.py  config.py  display.py  login.py   # pure Python, unit-tested
  macos/      pasteboard.py hotkey.py   paste.py    popup.py    login_hud.py  app.py
tests/        unit tests for the pure modules (run anywhere)
scripts/      login-item.sh, copy_sensitive.py (manual test helper),
              render_screenshots.py (regenerates the images in docs/)
```

```sh
uv run pytest
```

### Manual test checklist (macOS)

1. Copy 12 distinct lines in TextEdit, then press ⌥⌘V. Expect exactly 10 recent items, numbered 1–0.
   Pin one (⌘P), copy 12 more lines, and check that the pin is still there as `a`.
2. In TextEdit, press ⌥⌘V then `3`. The third item is pasted at the cursor and shows as `1` next time.
   Repeat with ↑↓ + ⏎, with a click, and with a letter for a pinned item.
3. Check ⌘P (unpin), ⌫ (delete), **Clear history** (pins remain), and **Clear everything** (empty).
4. Run `uv run python scripts/copy_sensitive.py`, then open the popup. The text must not appear.
   Repeat with `--transient`. Then copy a password from Passwords or 1Password, if one is installed.
5. Turn Accessibility off. Picking an item copies it and shows "press ⌘V". Turn it back on,
   restart clipmgr, and check that auto-paste works.
6. Gmail (user-supervised): paste into a draft from the popup. Check the text, **do not send**,
   then discard the draft.
7. Quit and relaunch. The history is empty.
8. **Login helper.** Open any login page. Press ⌃⌘L, copy a username from a note, then copy a
   password from your password manager. Check that the panel ticks off both, and that ⌥⌘V
   doesn't list them. Click the username field and press ⌃⌘L, then Tab and ⌃⌘L. Both values
   should be pasted, and the panel should show "Done". In TextEdit, ⌘V should paste what was
   on your clipboard before you started.
9. **Password field.** With the password field selected, check whether ⌃⌘L works. If it
   doesn't, clicking **Password** in the panel must work.
10. **Login helper edge cases.** ⇅ Swap, Cancel, ⌃⌘L while it's waiting for copies, and
    letting the countdown run out. Each one should wipe or fix the values as described above.

## Known limitations (v1)

- Plain text only (no images, files, RTF/HTML). No sync, no persistence.
- Auto-paste sends the physical V key (ANSI key code 9). Non-QWERTY layouts such as Dvorak
  may paste the wrong shortcut.
- macOS shows the app as "Python" (or your terminal app) in Settings, not as "clipmgr".

## Phase 2 ideas

- A real `.app` bundle (py2app) so clipmgr has its own name and icon in the Accessibility and
  Login Items lists.
