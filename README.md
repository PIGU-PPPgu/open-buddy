# open-buddy

A multi-agent hardware buddy for M5Stack StickS3.

Supports **Claude Code**, **Codex**, **OpenClaw**, **Hermes** and more — all at once.
When multiple agents are running, the device always shows what needs your attention most.

## Features

- **Multi-agent priority display** — attention > busy > idle, with agent name shown
- **Sound alerts** — distinct tones for approval requests, task complete, errors
- **Mute mode** — toggle silence from the device menu
- **BLE bridge** — macOS daemon connects all agents to the device over Bluetooth

## Hardware

M5Stack StickS3 (ESP32-S3)

## Quick Start

### 1. Flash firmware

Download `open-buddy-sticks3-vX.X.X-full.bin` from [Releases](https://github.com/PIGU-PPPgu/open-buddy/releases) and flash:

```bash
esptool --chip esp32s3 --port /dev/cu.usbmodem1101 --baud 460800 \
  write_flash 0x0 open-buddy-sticks3-vX.X.X-full.bin
```

### 2. Install bridge

```bash
pip install open-buddy
open-buddy pair
open-buddy agent &
```

### 3. Install agent hooks

```bash
open-buddy hooks install --all   # installs for all detected agents
open-buddy hooks install --cc    # Claude Code only
open-buddy hooks install --codex # Codex only
```

## Agent Support

| Agent | Status | Hook path |
|-------|--------|-----------|
| Claude Code | Planned | `~/.claude/settings.json` |
| Codex | Planned | `~/.codex/config.toml` |
| OpenClaw | Planned | `~/.openclaw/settings.json` |
| Hermes | Planned | `~/.hermes/settings.json` |

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
| Approval needed | Alert tone (repeating) |
| Task complete | Success chime |
| Error / denied | Low buzz |
| Mute toggled | Single click |

## Controls

| Button | Action |
|--------|--------|
| A (front) | Approve / next screen |
| B (right) | Deny / scroll |
| Hold A | Menu |
| Power short | Toggle screen |
| Face down | Nap mode |

## Architecture

```
Claude Code ──┐
Codex        ──┤ hooks → open-buddy agent (macOS) ──BLE──> StickS3
OpenClaw     ──┤
Hermes       ──┘
```

The bridge runs as a macOS background agent. Each coding agent fires hooks on
session start, tool use, approval requests, and stop. The bridge aggregates
all events, applies priority logic, and pushes state to the device over BLE.

## Contributing

PRs welcome. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for internals.

## License

MIT
