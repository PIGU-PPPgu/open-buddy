"""
Voice input: delegate to voice-helper.py running in GUI session.
"""
from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger(__name__)

VOICE_SOCK = os.path.expanduser("~/.open-buddy/voice.sock")


async def _send(cmd: str) -> None:
    if not os.path.exists(VOICE_SOCK):
        log.warning("voice-helper not running (socket missing: %s)", VOICE_SOCK)
        return
    try:
        r, w = await asyncio.open_unix_connection(VOICE_SOCK)
        w.write(cmd.encode())
        await w.drain()
        w.close()
        await w.wait_closed()
    except Exception as e:
        log.warning("voice-helper error: %s", e)


async def trigger_macos_dictation() -> None:
    await _send("start")
    log.info("voice start sent to helper")


async def trigger_macos_dictation_stop() -> None:
    await _send("stop")
    log.info("voice stop sent to helper")
