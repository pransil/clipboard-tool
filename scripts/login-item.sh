#!/bin/bash
# Start clipmgr automatically when you log in, using a per-user LaunchAgent.
#
#   scripts/login-item.sh install     # install, and start it now
#   scripts/login-item.sh restart     # restart it (e.g. after granting Accessibility)
#   scripts/login-item.sh status      # is it running? show recent log lines
#   scripts/login-item.sh uninstall   # stop it and stop starting at login
#   scripts/login-item.sh plist       # print the LaunchAgent it would install
#
# The agent runs this checkout's .venv Python, so re-run "install" if you move
# the project folder. It restarts clipmgr if it crashes, but not after you
# choose Quit from the menu bar.
set -euo pipefail

LABEL="local.clipmgr"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/clipmgr.log"
DOMAIN="gui/$(id -u)"

xml_escape() {
    local s=$1
    s=${s//&/&amp;}
    s=${s//</&lt;}
    s=${s//>/&gt;}
    printf '%s' "$s"
}

is_loaded() {
    launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1
}

warn_other_instances() {
    local pids
    pids=$(pgrep -f -- "-m clipmgr" || true)
    if [[ -n "$pids" ]]; then
        echo "Note: clipmgr is also running outside launchd (pid $pids)."
        echo "      Quit that copy (menu bar icon → Quit clipmgr) so only one is running."
    fi
}

plist_contents() {
    cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$(xml_escape "$PYTHON")</string>
        <string>-m</string>
        <string>clipmgr</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$(xml_escape "$PROJECT_DIR")</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>ProcessType</key>
    <string>Interactive</string>
    <key>LimitLoadToSessionType</key>
    <string>Aqua</string>
    <key>StandardOutPath</key>
    <string>$(xml_escape "$LOG")</string>
    <key>StandardErrorPath</key>
    <string>$(xml_escape "$LOG")</string>
</dict>
</plist>
EOF
}

install() {
    case "$PROJECT_DIR" in
        "$HOME/Desktop"*|"$HOME/Documents"*|"$HOME/Downloads"*)
            echo "Warning: the project is in a privacy-protected folder ($PROJECT_DIR)."
            echo "         macOS may block Python from reading it at login. Consider moving it."
            ;;
    esac

    echo "Syncing the virtual environment…"
    (cd "$PROJECT_DIR" && uv sync --quiet)
    "$PYTHON" -c "import clipmgr" || { echo "clipmgr is not importable from $PYTHON" >&2; exit 1; }

    if is_loaded; then
        launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
        sleep 1
    fi
    warn_other_instances

    mkdir -p "$(dirname "$PLIST")" "$(dirname "$LOG")"
    plist_contents >"$PLIST"
    plutil -lint -s "$PLIST"
    launchctl bootstrap "$DOMAIN" "$PLIST"

    cat <<EOF
Installed $PLIST
clipmgr is starting now and will start every time you log in.

Next: allow it to paste. When macOS asks, or in System Settings → Privacy &
Security → Accessibility, turn on "Python". Then run: $0 restart
EOF
}

uninstall() {
    if is_loaded; then
        launchctl bootout "$DOMAIN/$LABEL"
    fi
    rm -f "$PLIST"
    echo "Removed. clipmgr will no longer start at login."
}

restart() {
    if ! is_loaded; then
        echo "Not installed. Run: $0 install" >&2
        exit 1
    fi
    launchctl kickstart -k "$DOMAIN/$LABEL"
    echo "Restarted."
}

python_app() {
    # The app macOS shows as "Python" under Privacy & Security → Accessibility.
    "$PYTHON" -c 'import sys, pathlib
exe = pathlib.Path(sys._base_executable).resolve()
app = exe.parent.parent / "Resources" / "Python.app"
print(app if app.exists() else exe)' 2>/dev/null || echo "(run: uv sync)"
}

status() {
    echo "Accessibility app (\"Python\"): $(python_app)"
    if is_loaded; then
        launchctl print "$DOMAIN/$LABEL" | grep -E '^\s*(state|pid|last exit code) =' || true
    else
        echo "Not installed as a login item."
    fi
    if [[ -f "$LOG" ]]; then
        echo "--- last lines of $LOG"
        tail -n 5 "$LOG"
    fi
}

case "${1:-}" in
    install) install ;;
    uninstall) uninstall ;;
    restart) restart ;;
    status) status ;;
    plist) plist_contents ;;
    *)
        sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
        exit 2
        ;;
esac
