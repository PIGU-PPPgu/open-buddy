"""
Claude Code agent adapter.
Receives hook events via Unix socket and forwards to Router.

Hook events fired by Claude Code (settings.json):
  PreToolUse, PostToolUse, UserPromptSubmit, Stop, Notification
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..router import Router

log = logging.getLogger(__name__)

SOCKET_PATH = Path.home() / ".open-buddy" / "cc.sock"


class ClaudeCodeAdapter:
    def __init__(self, router: "Router") -> None:
        self._router = router

    async def serve(self) -> None:
        SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()
        server = await asyncio.start_unix_server(self._handle, path=str(SOCKET_PATH))
        log.info("Claude Code adapter listening on %s", SOCKET_PATH)
        async with server:
            await server.serve_forever()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            data = await reader.read(65536)
            event = json.loads(data)
            await self._dispatch(event)
        except Exception as exc:
            log.warning("cc adapter error: %s", exc)
        finally:
            writer.close()

    async def _dispatch(self, event: dict) -> None:
        hook = event.get("hook_event_name", "")
        session_id = event.get("session_id", "unknown-cc")
        agent = "cc"

        if hook == "UserPromptSubmit":
            self._router.on_session_start(agent, session_id)

        elif hook == "PreToolUse":
            tool = event.get("tool_name", "")
            tool_input = event.get("tool_input", {})
            # Build a short display message
            if isinstance(tool_input, dict):
                # Show the most meaningful field: command, file_path, description, etc.
                hint = (
                    tool_input.get("command")
                    or tool_input.get("file_path")
                    or tool_input.get("description")
                    or tool_input.get("query")
                    or ""
                )
                msg = f"{tool}: {str(hint)[:80]}" if hint else tool
            else:
                msg = tool
            # Permission tools trigger attention state
            if "permission" in tool.lower() or tool in ("Bash", "Write", "Edit"):
                self._router.on_attention(session_id, msg)
            else:
                self._router.on_busy(session_id, msg)

        elif hook == "PostToolUse":
            tool = event.get("tool_name", "")
            self._router.on_busy(session_id, f"✓ {tool}")

        elif hook == "Stop":
            reason = event.get("stop_reason", "")
            # Try to grab the last assistant text from transcript
            transcript = event.get("transcript", [])
            last_text = ""
            for msg in reversed(transcript):
                if msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        last_text = content[:200]
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                last_text = block.get("text", "")[:200]
                                break
                    if last_text:
                        break
            if reason == "end_turn":
                self._router.on_celebrate(session_id, last_text)
            self._router.on_session_stop(session_id)

        elif hook == "Notification":
            msg = event.get("message", "")
            self._router.on_attention(session_id, msg)
