"""
BLE transport — direct bleak connection to StickS3 via Nordic UART Service.
No helper app required.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from bleak import BleakClient, BleakScanner

log = logging.getLogger(__name__)

NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID      = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # write (Mac→device)
NUS_TX_UUID      = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # notify (device→Mac)

SND_ATTENTION = "attention"
SND_CELEBRATE = "celebrate"
SND_ERROR     = "error"
SND_MUTE      = "mute"


class BLEBridge:
    def __init__(self, device_id: str) -> None:
        self._device_id = device_id
        self._mute = False
        self._client: Optional[BleakClient] = None

    @property
    def mute(self) -> bool:
        return self._mute

    async def connect(self) -> None:
        if self._client and self._client.is_connected:
            return
        log.info("BLE scanning for %s …", self._device_id)
        client = BleakClient(self._device_id, disconnected_callback=self._on_disconnect)
        await client.connect(timeout=20.0)
        self._client = client
        owner = os.environ.get("USER", "open-buddy")[:31]
        await self._write_json({"cmd": "owner", "name": owner})
        log.info("BLE connected to %s", self._device_id)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.disconnect()
            self._client = None

    def _on_disconnect(self, _client: BleakClient) -> None:
        log.warning("BLE disconnected — will reconnect on next push")
        self._client = None

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

        running = 1 if state in ("busy", "attention", "celebrate") else 0
        waiting = 1 if state == "attention" else 0

        await self._write_json({
            "type": "snapshot",
            "running": running,
            "waiting": waiting,
            "total": running,
            "tokens": 0,
            "tokens_today": 0,
            "agent": agent,
            "msg": f"[{agent}] {approval_prompt or ''}"[:80] if agent else "",
            "entries": [f"[{agent}]"] if agent else [],
        })

        if state == "attention" and approval_prompt:
            await self._write_json({
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

    async def _send_sound(self, event: str) -> None:
        await self._ensure_connected()
        await self._write_json({"type": "sound", "event": event})

    async def _ensure_connected(self) -> None:
        if not self._client or not self._client.is_connected:
            try:
                await self.connect()
            except Exception as exc:
                log.warning("BLE connect failed (will retry): %s", exc)
                raise

    async def _write_json(self, payload: dict) -> None:
        if not self._client:
            return
        line = (json.dumps(payload, separators=(",", ":")) + "\n").encode()
        # BLE MTU is typically 20 bytes; chunk if needed
        chunk = 200
        for i in range(0, len(line), chunk):
            await self._client.write_gatt_char(NUS_RX_UUID, line[i:i+chunk], response=False)
