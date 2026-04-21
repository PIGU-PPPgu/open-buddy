"""
Router unit tests — requirement-driven.

Requirements covered:
1. No sessions → SLEEP
2. One busy session → BUSY
3. One attention session → ATTENTION
4. attention beats busy when both present
5. Most recently active wins at same priority
6. Session stop removes it from routing
7. Celebrate state is returned correctly
"""

import time
import pytest
from bridge.router import Router, State


def test_no_sessions_returns_sleep():
    r = Router()
    state, agent, prompt = r.resolve()
    assert state == State.SLEEP
    assert agent == ""


def test_single_busy_session():
    r = Router()
    r.on_session_start("cc", "s1")
    state, agent, _ = r.resolve()
    assert state == State.BUSY
    assert agent == "cc"


def test_attention_beats_busy():
    r = Router()
    r.on_session_start("cc", "s1")
    r.on_session_start("codex", "s2")
    r.on_attention("s1", "approve this?")
    state, agent, prompt = r.resolve()
    assert state == State.ATTENTION
    assert agent == "cc"
    assert prompt == "approve this?"


def test_most_recent_wins_same_priority():
    r = Router()
    r.on_session_start("cc", "s1")
    time.sleep(0.01)
    r.on_session_start("codex", "s2")
    r.on_busy("s2")
    state, agent, _ = r.resolve()
    assert state == State.BUSY
    assert agent == "codex"


def test_session_stop_removes_session():
    r = Router()
    r.on_session_start("cc", "s1")
    r.on_session_stop("s1")
    state, _, _ = r.resolve()
    assert state == State.SLEEP


def test_celebrate_state():
    r = Router()
    r.on_session_start("cc", "s1")
    r.on_celebrate("s1")
    state, agent, _ = r.resolve()
    assert state == State.CELEBRATE
    assert agent == "cc"


def test_approve_clears_attention():
    r = Router()
    r.on_session_start("cc", "s1")
    r.on_attention("s1", "approve?")
    r.on_approve("s1")
    state, _, prompt = r.resolve()
    assert state == State.BUSY
    assert prompt is None
