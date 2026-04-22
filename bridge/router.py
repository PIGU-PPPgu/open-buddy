"""
Event router — aggregates events from all agents and applies priority logic.

Priority: attention > busy > idle
Same-priority: most recently active agent wins.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


class State(IntEnum):
    SLEEP = 0
    IDLE = 1
    BUSY = 2
    ATTENTION = 3
    CELEBRATE = 4


@dataclass
class AgentSession:
    agent: str          # "cc" | "codex" | "claw" | "hermes"
    session_id: str
    state: State = State.IDLE
    last_active: float = field(default_factory=time.time)
    pending_approval: Optional[str] = None  # approval prompt text if any
    last_msg: str = ""  # latest status/tool message for display


class Router:
    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}  # session_id -> session

    # ------------------------------------------------------------------
    # Public API called by agent adapters
    # ------------------------------------------------------------------

    def on_session_start(self, agent: str, session_id: str) -> None:
        self._sessions[session_id] = AgentSession(
            agent=agent, session_id=session_id, state=State.BUSY
        )
        self._touch(session_id)

    def on_busy(self, session_id: str, msg: str = "") -> None:
        if s := self._sessions.get(session_id):
            s.state = State.BUSY
            if msg:
                s.last_msg = msg
            self._touch(session_id)

    def on_attention(self, session_id: str, prompt: str) -> None:
        if s := self._sessions.get(session_id):
            s.state = State.ATTENTION
            s.pending_approval = prompt
            s.last_msg = prompt
            self._touch(session_id)

    def on_approve(self, session_id: str) -> None:
        if s := self._sessions.get(session_id):
            s.state = State.BUSY
            s.pending_approval = None
            self._touch(session_id)

    def on_celebrate(self, session_id: str, msg: str = "") -> None:
        if s := self._sessions.get(session_id):
            s.state = State.CELEBRATE
            if msg:
                s.last_msg = msg
            self._touch(session_id)

    def on_session_stop(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    # ------------------------------------------------------------------
    # Priority resolution
    # ------------------------------------------------------------------

    def resolve(self) -> tuple[State, str, Optional[str], str]:
        """
        Returns (state, agent_label, approval_prompt, last_msg).
        agent_label is empty string when no sessions exist.
        """
        if not self._sessions:
            return State.SLEEP, "", None, ""

        # Sort by priority desc, then last_active desc
        ranked = sorted(
            self._sessions.values(),
            key=lambda s: (s.state, s.last_active),
            reverse=True,
        )
        top = ranked[0]
        return top.state, top.agent, top.pending_approval, top.last_msg

    # ------------------------------------------------------------------

    def _touch(self, session_id: str) -> None:
        if s := self._sessions.get(session_id):
            s.last_active = time.time()
