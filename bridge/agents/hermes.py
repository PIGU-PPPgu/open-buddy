"""
Hermes agent adapter.
Hermes uses HTTP webhooks rather than file hooks.
We run a local HTTP server; the user registers it via:
  hermes webhook add http://localhost:7779/hermes
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from ..router import Router

log = logging.getLogger(__name__)

HERMES_PORT = 7779
HERMES_PATH = "/hermes"


class HermesAdapter:
    def __init__(self, router: "Router") -> None:
        self._router = router

    async def serve(self) -> None:
        app = web.Application()
        app.router.add_post(HERMES_PATH, self._handle)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", HERMES_PORT)
        await site.start()
        log.info("Hermes adapter listening on http://127.0.0.1:%d%s", HERMES_PORT, HERMES_PATH)
        # Keep running forever
        import asyncio
        await asyncio.Event().wait()

    async def _handle(self, request: web.Request) -> web.Response:
        try:
            event = await request.json()
            await self._dispatch(event)
        except Exception as exc:
            log.warning("hermes adapter error: %s", exc)
        return web.Response(status=200)

    async def _dispatch(self, event: dict) -> None:
        # Hermes webhook payload shape (best-effort mapping):
        # { "event": "session_start"|"tool_use"|"tool_result"|"session_end"|"approval_request",
        #   "session_id": "...", "tool": "...", "input": {...}, "approved": bool }
        ev = event.get("event", "")
        session_id = event.get("session_id", "unknown-hermes")
        agent = "hermes"

        if ev == "session_start":
            self._router.on_session_start(agent, session_id)

        elif ev == "tool_use":
            tool = event.get("tool", "")
            if tool in ("bash", "write", "edit") or "permission" in tool.lower():
                prompt = f"{tool}: {json.dumps(event.get('input', {}))[:120]}"
                self._router.on_attention(session_id, prompt)
            else:
                self._router.on_busy(session_id)

        elif ev == "tool_result":
            self._router.on_busy(session_id)

        elif ev == "approval_request":
            tool = event.get("tool", "")
            prompt = f"{tool}: {json.dumps(event.get('input', {}))[:120]}"
            self._router.on_attention(session_id, prompt)

        elif ev == "session_end":
            if event.get("completed", False):
                self._router.on_celebrate(session_id)
            self._router.on_session_stop(session_id)
