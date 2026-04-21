"""
BLE transport — wraps CodeBuddy's BLE protocol to push state to StickS3.

Payload format (Nordic UART, newline-delimited JSON):
  {"type": "state", "state": "busy", "agent": "cc", "mute": false}
  {"type": "approval", "prompt": "...", "agent": "codex"}
  {"type": "sound", "event": "attention"|"celebrate"|"error"|"mute"}
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

log = logging.getLogger(__name__)

# Sound event constants
SND_ATTENTION = "attention"
SND_CELEBRATE = "celebrate"
SND_ERROR = "error"
SND_MUTE = "mute"


class BLEBridge:
    def __init__(self, device_id: str) -> None:
        self._device_id = device_id
        self._mute = False
        self._writer: Optional[asyncio.StreamWriter] = None
        # TODO: connect via CodeBuddyBLEHelper socket

    @property
    def mute(self) -> bool:
        return self._mute

    def toggle_mute(self) -> bool:
        self._mute = not self._mute
        asyncio.create_task(self._send({"type": "sound", "event": SND_MUTE}))
        return self._mute

    async def push_state(
        self,
        state: str,
        agent: str,
        approval_prompt: Optional[str] = None,
    ) -> None:
        payload: dict = {"type": "state", "state": state, "agent": agent, "mute": self._mute}
        await self._send(payload)

        if state == "attention" and approval_prompt is not None:
            await self._send({"type": "approval", "prompt": approval_prompt, "agent": agent})
            if not self._mute:
                await self._send({"type": "sound", "event": SND_ATTENTION})

        elif state == "celebrate":
            if not self._mute:
                await self._send({"type": "sound", "event": SND_CELEBRATE})

    async def push_error(self, agent: str) -> None:
        if not self._mute:
            await self._send({"type": "sound", "event": SND_ERROR})

    async def _send(self, payload: dict) -> None:
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        log.debug("BLE tx: %s", line.rstrip())
        # TODO: write to BLE socket
