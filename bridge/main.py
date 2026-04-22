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
from .agents.openclaw import OpenClawAdapter
from .agents.hermes import HermesAdapter

log = logging.getLogger(__name__)

POLL_INTERVAL = 0.5  # seconds between state pushes


async def run(device_id: str) -> None:
    router = Router()
    ble = BLEBridge(device_id)

    adapters = [
        ClaudeCodeAdapter(router),
        CodexAdapter(router),
        OpenClawAdapter(router),
        HermesAdapter(router),
    ]

    adapter_tasks = [asyncio.create_task(a.serve()) for a in adapters]

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
    sub = parser.add_subparsers(dest="cmd")

    # run subcommand
    run_p = sub.add_parser("run", help="Start the bridge daemon")
    run_p.add_argument("--device", required=True, help="BLE device UUID")
    run_p.add_argument("--debug", action="store_true")

    # hooks subcommand
    hooks_p = sub.add_parser("hooks", help="Manage agent hook configs")
    hooks_sub = hooks_p.add_subparsers(dest="hooks_cmd")
    install_p = hooks_sub.add_parser("install", help="Install hooks into all agent configs")
    install_p.add_argument(
        "--agent",
        choices=["all", "cc", "claw", "codex", "hermes"],
        default="all",
    )

    # Legacy: bare --device flag for backwards compat
    parser.add_argument("--device", help=argparse.SUPPRESS)
    parser.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()

    # Legacy invocation: open-buddy --device <uuid>
    if args.cmd is None and args.device:
        args.cmd = "run"

    if args.cmd == "run" or (args.cmd is None and args.device):
        logging.basicConfig(
            level=logging.DEBUG if args.debug else logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        asyncio.run(run(args.device))

    elif args.cmd == "hooks" and args.hooks_cmd == "install":
        from .hooks_installer import (
            install_all, install_claude_code, install_openclaw,
            install_codex, install_hermes,
        )
        dispatch = {
            "all": install_all,
            "cc": install_claude_code,
            "claw": install_openclaw,
            "codex": install_codex,
            "hermes": install_hermes,
        }
        dispatch[args.agent]()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
