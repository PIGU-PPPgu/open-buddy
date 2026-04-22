"""
Voice input: device double-tap → trigger macOS dictation (Fn Fn).
"""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)


async def trigger_macos_dictation() -> None:
    """Simulate pressing Fn twice to invoke macOS dictation."""
    script = """
tell application "System Events"
    key code 63
    delay 0.05
    key code 63
end tell
"""
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", script,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        log.warning("osascript failed: %s", err.decode().strip())
    else:
        log.info("macOS dictation triggered")
