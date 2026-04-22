"""
open-buddy hooks installer.
Injects hook entries into each agent's settings file so events are forwarded
to the bridge's Unix sockets.
"""

from __future__ import annotations

import json
from pathlib import Path


def _socket_cmd(agent: str) -> str:
    sock = Path.home() / ".open-buddy" / f"{agent}.sock"
    # Pipe the hook JSON payload into the Unix socket via nc
    return f"cat | nc -U {sock}"


# ---------------------------------------------------------------------------
# Hook payloads for Claude Code / OpenClaw (identical format)
# ---------------------------------------------------------------------------

_CC_HOOKS = {
    "hooks": {
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": _socket_cmd("cc")}]}],
        "PreToolUse":       [{"hooks": [{"type": "command", "command": _socket_cmd("cc")}]}],
        "PostToolUse":      [{"hooks": [{"type": "command", "command": _socket_cmd("cc")}]}],
        "Stop":             [{"hooks": [{"type": "command", "command": _socket_cmd("cc")}]}],
        "Notification":     [{"hooks": [{"type": "command", "command": _socket_cmd("cc")}]}],
    }
}

_CLAW_HOOKS = {
    "hooks": {
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": _socket_cmd("claw")}]}],
        "PreToolUse":       [{"hooks": [{"type": "command", "command": _socket_cmd("claw")}]}],
        "PostToolUse":      [{"hooks": [{"type": "command", "command": _socket_cmd("claw")}]}],
        "Stop":             [{"hooks": [{"type": "command", "command": _socket_cmd("claw")}]}],
        "Notification":     [{"hooks": [{"type": "command", "command": _socket_cmd("claw")}]}],
    }
}


def _socket_cmd(agent: str) -> str:
    sock = Path.home() / ".open-buddy" / f"{agent}.sock"
    # Pipe the hook JSON payload into the Unix socket via nc
    return f"cat | nc -U {sock}"


def _merge_hooks(existing: dict, additions: dict) -> dict:
    """Deep-merge additions into existing hooks dict without duplicating entries."""
    result = dict(existing)
    hooks_section = dict(result.get("hooks", {}))
    for event, new_entries in additions.get("hooks", {}).items():
        current = list(hooks_section.get(event, []))
        for entry in new_entries:
            cmd = entry["hooks"][0]["command"]
            # Skip if already present
            if not any(
                e.get("hooks", [{}])[0].get("command") == cmd
                for e in current
            ):
                current.append(entry)
        hooks_section[event] = current
    result["hooks"] = hooks_section
    return result


def install_claude_code() -> None:
    settings_path = Path.home() / ".claude" / "settings.json"
    _install(settings_path, _CC_HOOKS, "Claude Code")


def install_openclaw() -> None:
    settings_path = Path.home() / ".openclaw" / "settings.json"
    _install(settings_path, _CLAW_HOOKS, "OpenClaw")


def install_codex() -> None:
    # Codex uses ~/.codex/config.toml — hooks are registered differently.
    # The codex adapter uses its own socket; codex hook config is TOML-based.
    # For now, print instructions.
    sock = Path.home() / ".open-buddy" / "codex.sock"
    print(
        "Codex: add the following to ~/.codex/config.toml:\n\n"
        "[hooks]\n"
        f'session_start = "cat | nc -U {sock}"\n'
        f'user_prompt_submit = "cat | nc -U {sock}"\n'
        f'approval_request = "cat | nc -U {sock}"\n'
        f'stop = "cat | nc -U {sock}"\n'
    )


def install_hermes() -> None:
    print(
        "Hermes: register the webhook with:\n\n"
        "  hermes webhook add http://localhost:7779/hermes\n"
    )


def _install(path: Path, additions: dict, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except json.JSONDecodeError:
            print(f"Warning: {path} is not valid JSON — backing up and overwriting")
            path.rename(path.with_suffix(".json.bak"))

    merged = _merge_hooks(existing, additions)
    path.write_text(json.dumps(merged, indent=2))
    print(f"{label}: hooks installed → {path}")


def install_all() -> None:
    install_claude_code()
    install_openclaw()
    install_codex()
    install_hermes()
