"""
BLE transport — connects to StickS3 via CodeBuddyBLEHelper (native macOS BLE).

Reuses CodeBuddy's NativeBleHelperSession and wire protocol (Nordic UART Service).
State payload mirrors CodeBuddy's snapshot format so the existing firmware works
without modification.

Sound events are sent as a custom "sound" command; firmware support is added
separately in the open-buddy firmware fork.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Nordic UART Service UUIDs (same as CodeBuddy)
NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

# Sound event names (must match firmware handler)
SND_ATTENTION = "attention"
SND_CELEBRATE = "celebrate"
SND_ERROR = "error"
SND_MUTE = "mute"

HELPER_APP_PATH = Path.home() / ".code-buddy" / "helper" / "CodeBuddyBLEHelper.app"


def _get_helper_path() -> Path:
    override = os.environ.get("OPEN_BUDDY_BLE_HELPER_APP", "").strip()
    if override:
        return Path(override).expanduser()
    if HELPER_APP_PATH.exists():
        return HELPER_APP_PATH
    raise RuntimeError(
        f"CodeBuddyBLEHelper not found at {HELPER_APP_PATH}.\n"
        "Run: open-buddy setup"
    )


class BLEBridge:
    def __init__(self, device_id: str) -> None:
        self._device_id = device_id
        self._mute = False
        self._session: Optional[_NativeSession] = None

    @property
    def mute(self) -> bool:
        return self._mute

    async def connect(self) -> None:
        if self._session and self._session.is_connected:
            return
        self._session = _NativeSession(
            device_id=self._device_id,
            helper_path=_get_helper_path(),
        )
        await self._session.connect()
        await self._session.write_json({"cmd": "owner", "name": os.environ.get("USER", "open-buddy")[:31]})
        log.info("BLE connected to %s", self._device_id)

    async def disconnect(self) -> None:
        if self._session:
            await self._session.disconnect()
            self._session = None

    def toggle_mute(self) -> bool:
        self._mute = not self._mute
        asyncio.create_task(self._send_sound(SND_MUTE))
        return self._mute

    async def push_state(
        self,
        state: str,
        agent: str,
        approval_prompt: Optional[str] = None,
    ) -> None:
        await self._ensure_connected()

        # Map our state names to CodeBuddy snapshot format so existing firmware works
        running = 1 if state in ("busy", "attention", "celebrate") else 0
        waiting = 1 if state == "attention" else 0

        snapshot_payload = {
            "type": "snapshot",
            "running": running,
            "waiting": waiting,
            "total": running,
            "tokens": 0,
            "tokens_today": 0,
            "agent": agent,
            "msg": f"[{agent}] {approval_prompt or ''}"[:80] if agent else "",
            "entries": [f"[{agent}]"] if agent else [],
        }
        await self._session.write_json(snapshot_payload)  # type: ignore[union-attr]

        if state == "attention" and approval_prompt:
            await self._session.write_json({  # type: ignore[union-attr]
                "type": "permission",
                "prompt": approval_prompt[:200],
                "agent": agent,
            })
            if not self._mute:
                await self._send_sound(SND_ATTENTION)

        elif state == "celebrate":
            if not self._mute:
                await self._send_sound(SND_CELEBRATE)

    async def push_error(self, agent: str) -> None:
        if not self._mute:
            await self._send_sound(SND_ERROR)

    # ------------------------------------------------------------------

    async def _send_sound(self, event: str) -> None:
        await self._ensure_connected()
        await self._session.write_json({"type": "sound", "event": event})  # type: ignore[union-attr]

    async def _ensure_connected(self) -> None:
        if not self._session or not self._session.is_connected:
            await self.connect()


# ---------------------------------------------------------------------------
# Minimal NativeBleHelperSession — drives CodeBuddyBLEHelper.app via
# the same file-based IPC protocol used by CodeBuddy's Python bridge.
# ---------------------------------------------------------------------------

import contextlib
import json
import subprocess
import time


class _NativeSession:
    """Drives CodeBuddyBLEHelper.app via file-based IPC (same as CodeBuddy)."""

    def __init__(self, *, device_id: str, helper_path: Path) -> None:
        self._device_id = device_id
        self._helper_path = helper_path
        self._connected = False
        self._session_dir: Optional[Path] = None
        self._commands_dir: Optional[Path] = None
        self._events_path: Optional[Path] = None
        self._pump_task: Optional[asyncio.Task] = None
        self._next_seq = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._connect_error: Optional[Exception] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self, timeout: float = 15.0) -> None:
        if self._connected:
            return
        self._session_dir = Path(tempfile.mkdtemp(prefix="open-buddy-ble-"))
        self._commands_dir = self._session_dir / "commands"
        self._events_path = self._session_dir / "events.jsonl"
        self._commands_dir.mkdir(parents=True, exist_ok=True)
        self._events_path.write_text("")

        subprocess.run(
            [
                "open", "-n", str(self._helper_path),
                "--args",
                "--session-dir", str(self._session_dir),
                "--device-id", self._device_id,
                "--device-name", "",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        self._pump_task = asyncio.create_task(self._pump_events())

        deadline = asyncio.get_running_loop().time() + timeout
        while not self._connected:
            if self._connect_error:
                raise self._connect_error
            if asyncio.get_running_loop().time() >= deadline:
                raise RuntimeError("Timed out waiting for BLE helper to connect")
            await asyncio.sleep(0.05)

    async def write_json(self, payload: dict) -> None:
        line = json.dumps(payload, separators=(",", ":"))
        await self._send_command("write_json", line=line)

    async def disconnect(self) -> None:
        if self._pump_task and not self._pump_task.done():
            with contextlib.suppress(Exception):
                await self._send_command("shutdown")
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._pump_task, timeout=3.0)

    async def _send_command(self, cmd: str, **kwargs) -> None:
        if not self._commands_dir:
            return
        seq = self._next_seq
        self._next_seq += 1
        payload = {"seq": seq, "cmd": cmd, **kwargs}
        cmd_file = self._commands_dir / f"{seq:08d}.json"
        cmd_file.write_text(json.dumps(payload))

    async def _pump_events(self) -> None:
        assert self._events_path is not None
        offset = 0
        buffer = bytearray()
        while True:
            try:
                if self._events_path.exists():
                    with self._events_path.open("rb") as fh:
                        fh.seek(offset)
                        chunk = fh.read()
                    if chunk:
                        offset += len(chunk)
                        buffer.extend(chunk)
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            self._handle_event(json.loads(line))
            except Exception as exc:
                log.debug("pump error: %s", exc)
            await asyncio.sleep(0.05)

    def _handle_event(self, event: dict) -> None:
        etype = event.get("type", "")
        if etype == "connected":
            self._connected = True
        elif etype == "disconnected":
            self._connected = False
        elif etype == "ack":
            seq = event.get("seq")
            if seq in self._pending:
                self._pending.pop(seq).set_result(None)
        elif etype == "error" and not self._connected:
            self._connect_error = RuntimeError(event.get("message", "BLE error"))
