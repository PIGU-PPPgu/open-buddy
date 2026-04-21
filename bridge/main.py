"""
Main bridge daemon — starts all agent adapters and drives the BLE bridge.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from .router import Router, State
from .ble.transport import BLEBridge
from .agents.claude_code import ClaudeCodeAdapter
from .agents.codex import CodexAdapter

log = logging.getLogger(__name__)

POLL_INTERVAL = 0.5  # seconds between state pushes


async def run(device_id: str) -> None:
    router = Router()
    ble = BLEBridge(device_id)

    adapters = [
        ClaudeCodeAdapter(router),
        CodexAdapter(router),
        # OpenClawAdapter(router),  # TODO
        # HermesAdapter(router),    # TODO
    ]

    # Start all adapters concurrently
    adapter_tasks = [asyncio.create_task(a.serve()) for a in adapters]

    # State push loop
    last_state: tuple = (None, None, None)
    try:
        while True:
            current = router.resolve()
            if current != last_state:
                state, agent, prompt = current
                state_name = state.name.lower()
                log.info("state → %s [%s]", state_name, agent or "—")
                await ble.push_state(state_name, agent, prompt)
                last_state = current
            await asyncio.sleep(POLL_INTERVAL)
    finally:
        for t in adapter_tasks:
            t.cancel()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="open-buddy bridge")
    parser.add_argument("--device", required=True, help="BLE device UUID")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run(args.device))


if __name__ == "__main__":
    main()
