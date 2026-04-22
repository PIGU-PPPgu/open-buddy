"""
OpenClaw agent adapter.
OpenClaw is a Claude Code fork — identical hook format, different config path.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..router import Router

log = logging.getLogger(__name__)

SOCKET_PATH = Path.home() / ".open-buddy" / "claw.sock"
SETTINGS_PATH = Path.home() / ".openclaw" / "settings.json"


class OpenClawAdapter:
    def __init__(self, router: "Router") -> None:
        self._router = router

    async def serve(self) -> None:
        SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()
        server = await asyncio.start_unix_server(self._handle, path=str(SOCKET_PATH))
        log.info("OpenClaw adapter listening on %s", SOCKET_PATH)
        async with server:
            await server.serve_forever()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            data = await reader.read(65536)
            event = json.loads(data)
            await self._dispatch(event)
        except Exception as exc:
            log.warning("claw adapter error: %s", exc)
        finally:
            writer.close()

    async def _dispatch(self, event: dict) -> None:
        hook = event.get("hook_event_name", "")
        session_id = event.get("session_id", "unknown-claw")
        agent = "claw"

        if hook == "UserPromptSubmit":
            self._router.on_session_start(agent, session_id)

        elif hook == "PreToolUse":
            tool = event.get("tool_name", "")
            if "permission" in tool.lower() or tool in ("Bash", "Write", "Edit"):
                prompt = f"{tool}: {json.dumps(event.get('tool_input', {}))[:120]}"
                self._router.on_attention(session_id, prompt)
            else:
                self._router.on_busy(session_id)

        elif hook == "PostToolUse":
            self._router.on_busy(session_id)

        elif hook == "Stop":
            if event.get("stop_reason") == "end_turn":
                self._router.on_celebrate(session_id)
            self._router.on_session_stop(session_id)

        elif hook == "Notification":
            self._router.on_attention(session_id, event.get("message", ""))
