# open-buddy

A multi-agent hardware buddy for M5Stack StickS3, built on top of [CodeBuddy](https://github.com/CharlexH/CodeBuddy).

While CodeBuddy supports a single agent (Codex), open-buddy extends it to watch **Claude Code, Codex, OpenClaw, and Hermes simultaneously** — always surfacing what needs your attention most.

## What's new vs CodeBuddy

| | CodeBuddy | open-buddy |
|---|---|---|
| Agents | Codex only | Claude Code, Codex, OpenClaw, Hermes |
| Priority logic | Single session | Multi-agent: attention > busy > idle |
| Agent label | — | Active agent shown on device (cc / codex / claw / hermes) |
| Sound alerts | — | Distinct tones: approval / complete / error / mute |
| Mute mode | — | Toggle from device menu |
| BLE transport | CodeBuddyBLEHelper.app | Direct Python bleak — no helper app needed |
| macOS autostart | Manual | launchd service, starts at login |
| Hook installer | Manual | `open-buddy hooks install` auto-injects all agent configs |

Firmware is a fork of CodeBuddy's — same wire protocol, same display logic, with additions for agent labels and sound events.

## Hardware

M5Stack StickS3 (ESP32-S3)

## Quick Start

### 1. Flash firmware

Use [PlatformIO](https://platformio.org/):

```bash
cd firmware
pio run --target upload
```

Or download a pre-built `.bin` from [Releases](https://github.com/PIGU-PPPgu/open-buddy/releases) and flash with M5Burner.

### 2. One-command setup (macOS)

```bash
bash setup.sh --device <BLE-UUID>
```

This single command:
- Installs the Python bridge (`pip install -e .`)
- Compiles and installs `voice-helper` (Swift, requires Xcode CLT)
- Registers both as launchd services (auto-start at login)
- Installs hooks into all agent configs
- Triggers the one-time microphone + speech recognition permission dialogs

> **Prerequisites:** macOS, Xcode Command Line Tools (`xcode-select --install`), Python 3.10+

To find your device UUID, run `open-buddy run --device ?` or use a BLE scanner app.

### Manual setup (optional)

<details>
<summary>Step-by-step without setup.sh</summary>

```bash
# Install bridge
pip install open-buddy

# Install agent hooks
open-buddy hooks install

# Start bridge
open-buddy run --device <BLE-UUID>
```

To run at login, add a launchd plist pointing to `open-buddy run --device <UUID>`.

For voice input, compile and create the app bundle (required for TCC permissions):
```bash
mkdir -p ~/.open-buddy/VoiceHelper.app/Contents/MacOS
swiftc -O voice-helper.swift -o ~/.open-buddy/VoiceHelper.app/Contents/MacOS/VoiceHelper \
  -framework Foundation -framework Speech -framework AVFoundation \
  -framework AppKit -framework CoreGraphics
# Copy Info.plist into the bundle
cp docs/VoiceHelper-Info.plist ~/.open-buddy/VoiceHelper.app/Contents/Info.plist
```
Then load the LaunchAgent (uses `open -W -n -a` for proper TCC context):
```bash
launchctl bootstrap gui/$(id -u) docs/com.open-buddy.voice-helper.plist
```

</details>

## Agent Support

| Agent | Status | Config |
|-------|--------|--------|
| Claude Code | ✅ | `~/.claude/settings.json` |
| Codex | ✅ | `~/.codex/config.toml` |
| OpenClaw | ✅ | `~/.openclaw/settings.json` |
| Hermes | ✅ | `hermes webhook add http://localhost:7779/hermes` |

## Device States

| State | Trigger |
|-------|---------|
| `sleep` | No bridge connected |
| `idle` | Connected, nothing running |
| `busy` | Session(s) active |
| `attention` | Approval pending — LED blinks, sound plays |
| `celebrate` | Task complete |
| `dizzy` | Shake gesture |

## Sound Events

| Event | Sound |
|-------|-------|
| Approval needed | Two-tone alert |
| Task complete | Rising chime |
| Error / denied | Low descending buzz |
| Mute toggled | Single click |

## Controls

| Button | Action |
|--------|--------|
| A (front) | Approve prompt / next screen |
| B (right side) | Deny prompt / scroll / next page |
| B double-tap | Toggle voice input (start/stop recording) |
| Hold A | Menu |
| Power (short) | Toggle screen |
| Face down | Nap mode |

## Voice Input

Double-tap the B button to start recording. A green microphone pill appears on screen and a macOS-style overlay shows near the cursor. Double-tap again to stop — the transcribed text is typed into the frontmost app.

Powered by `SFSpeechRecognizer` (on-device, zh-CN by default). Change locale in `voice-helper.swift` line with `SFSpeechRecognizer(locale:)`.

## Architecture

```
Claude Code ──┐
Codex        ──┤  Unix sockets / HTTP  ┌─ priority router ─── BLE ──> StickS3
OpenClaw     ──┤ ────────────────────> │   (attention > busy > idle)
Hermes       ──┘                       └─ state push loop (0.5s)
```

The bridge runs as a background process. Each agent fires hooks on session start, tool use, approval requests, and stop. The router aggregates all sessions, picks the highest-priority state, and pushes it to the device over BLE (Nordic UART Service).

## Credits

Firmware and BLE wire protocol based on [CodeBuddy](https://github.com/CharlexH/CodeBuddy) by CharlexH.

## License

MIT
