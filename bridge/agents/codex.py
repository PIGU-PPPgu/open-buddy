"""
Codex agent adapter.
Receives hook events via Unix socket and forwards to Router.

Hook events: SessionStart, UserPromptSubmit, Stop
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

SOCKET_PATH = Path.home() / ".open-buddy" / "codex.sock"


class CodexAdapter:
    def __init__(self, router: "Router") -> None:
        self._router = router

    async def serve(self) -> None:
        SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()
        server = await asyncio.start_unix_server(self._handle, path=str(SOCKET_PATH))
        log.info("Codex adapter listening on %s", SOCKET_PATH)
        async with server:
            await server.serve_forever()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            data = await reader.read(65536)
            event = json.loads(data)
            await self._dispatch(event)
        except Exception as exc:
            log.warning("codex adapter error: %s", exc)
        finally:
            writer.close()

    async def _dispatch(self, event: dict) -> None:
        hook = event.get("type", "")
        session_id = event.get("session_id", "unknown-codex")
        agent = "codex"

        if hook == "SessionStart":
            self._router.on_session_start(agent, session_id)

        elif hook == "UserPromptSubmit":
            self._router.on_busy(session_id)

        elif hook == "approval_request":
            prompt = event.get("prompt", "Approval needed")
            self._router.on_attention(session_id, prompt)

        elif hook == "Stop":
            self._router.on_celebrate(session_id)
            self._router.on_session_stop(session_id)
