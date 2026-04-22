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

### 2. Install bridge

```bash
pip install open-buddy
```

### 3. Install agent hooks

```bash
open-buddy hooks install          # all agents
open-buddy hooks install --agent cc      # Claude Code only
open-buddy hooks install --agent codex   # Codex only
open-buddy hooks install --agent claw    # OpenClaw only
open-buddy hooks install --agent hermes  # Hermes (prints webhook URL)
```

### 4. Start bridge

```bash
open-buddy run --device <BLE-UUID>
```

To run at login (macOS), add a launchd plist pointing to `open-buddy run --device <UUID>`.

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
| Hold A | Menu |
| Power (short) | Toggle screen |
| Face down | Nap mode |

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
