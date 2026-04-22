#!/bin/bash
# open-buddy setup — run once after cloning
# Usage: bash setup.sh [--device <BLE-UUID>]
set -e

BUDDY_DIR="$HOME/.open-buddy"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[open-buddy]${NC} $*"; }
warn()  { echo -e "${YELLOW}[open-buddy]${NC} $*"; }
die()   { echo -e "${RED}[open-buddy]${NC} $*" >&2; exit 1; }

# ── Parse args ────────────────────────────────────────────────────────────────
DEVICE_UUID=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --device) DEVICE_UUID="$2"; shift 2 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

# ── 1. Python bridge ──────────────────────────────────────────────────────────
info "Installing Python bridge..."
pip install -e "$REPO_DIR" --quiet || die "pip install failed"

# ── 2. voice-helper binary ────────────────────────────────────────────────────
info "Compiling voice-helper..."
mkdir -p "$BUDDY_DIR"
swiftc -O "$REPO_DIR/voice-helper.swift" -o "$BUDDY_DIR/voice-helper" \
  -framework Foundation -framework Speech -framework AVFoundation \
  -framework AppKit -framework CoreGraphics \
  || die "swiftc failed — make sure Xcode Command Line Tools are installed (xcode-select --install)"
info "voice-helper compiled → $BUDDY_DIR/voice-helper"

# ── 3. LaunchAgent: voice-helper ──────────────────────────────────────────────
info "Installing voice-helper LaunchAgent..."
cat > "$LAUNCH_AGENTS/com.open-buddy.voice-helper.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.open-buddy.voice-helper</string>
    <key>ProgramArguments</key>
    <array>
        <string>$BUDDY_DIR/voice-helper</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/open-buddy-voice.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/open-buddy-voice.log</string>
    <key>ThrottleInterval</key>
    <integer>5</integer>
    <key>SessionCreate</key>
    <true/>
</dict>
</plist>
EOF
launchctl unload "$LAUNCH_AGENTS/com.open-buddy.voice-helper.plist" 2>/dev/null || true
launchctl load "$LAUNCH_AGENTS/com.open-buddy.voice-helper.plist"
info "voice-helper started (logs: /tmp/open-buddy-voice.log)"

# ── 4. LaunchAgent: bridge (optional, needs device UUID) ─────────────────────
if [[ -n "$DEVICE_UUID" ]]; then
  BRIDGE_BIN="$(which open-buddy 2>/dev/null || echo "")"
  [[ -z "$BRIDGE_BIN" ]] && die "open-buddy not found in PATH after pip install"

  info "Installing bridge LaunchAgent for device $DEVICE_UUID..."
  cat > "$LAUNCH_AGENTS/com.open-buddy.bridge.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.open-buddy.bridge</string>
    <key>ProgramArguments</key>
    <array>
        <string>$BRIDGE_BIN</string>
        <string>run</string>
        <string>--device</string>
        <string>$DEVICE_UUID</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/open-buddy.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/open-buddy.log</string>
    <key>ThrottleInterval</key>
    <integer>5</integer>
</dict>
</plist>
EOF
  launchctl unload "$LAUNCH_AGENTS/com.open-buddy.bridge.plist" 2>/dev/null || true
  launchctl load "$LAUNCH_AGENTS/com.open-buddy.bridge.plist"
  info "bridge started (logs: /tmp/open-buddy.log)"
else
  warn "No --device UUID given. Bridge not auto-started."
  warn "Run manually: open-buddy run --device <BLE-UUID>"
  warn "Or re-run: bash setup.sh --device <BLE-UUID>"
fi

# ── 5. Agent hooks ────────────────────────────────────────────────────────────
info "Installing agent hooks..."
open-buddy hooks install 2>/dev/null || warn "hooks install skipped (run manually: open-buddy hooks install)"

# ── 6. Permissions prompt ─────────────────────────────────────────────────────
echo ""
info "Requesting macOS permissions (one-time)..."
echo ""
echo "  Two permission dialogs will appear:"
echo "  1. Microphone — needed for voice input"
echo "  2. Speech Recognition — needed for transcription"
echo ""
echo "  Please click Allow on both."
echo ""

# Trigger permission requests by sending a test start command
# voice-helper will call SFSpeechRecognizer.requestAuthorization internally
sleep 1
if [[ -S "$BUDDY_DIR/voice.sock" ]]; then
  echo -n "start" | nc -U "$BUDDY_DIR/voice.sock" 2>/dev/null || true
  sleep 2
  echo -n "stop"  | nc -U "$BUDDY_DIR/voice.sock" 2>/dev/null || true
  info "Permission dialogs triggered — check for popups and click Allow."
else
  warn "voice.sock not ready yet — permissions will be requested on first use."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
info "Setup complete!"
echo ""
echo "  Voice input:  double-tap B button on device"
echo "  Approve:      tap A button"
echo "  Deny:         tap B button"
echo "  Logs:         tail -f /tmp/open-buddy.log"
echo "                tail -f /tmp/open-buddy-voice.log"
echo ""
