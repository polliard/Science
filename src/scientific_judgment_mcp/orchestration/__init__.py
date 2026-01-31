"""Orchestration package for multi-agent scientific deliberation."""

from .state_machine import (
    DebatePhase,
    AgentRole,
    VerdictDimension,
    AgentMessage,
    PaperContext,
    DebateState,
    PHASE_TRANSITIONS,
)

from .debate_protocol import (
    create_debate_graph,
    run_debate,
    run_debate_async,
)

__all__ = [
    "DebatePhase",
    "AgentRole",
    "VerdictDimension",
    "AgentMessage",
    "PaperContext",
    "DebateState",
    "PHASE_TRANSITIONS",
    "create_debate_graph",
    "run_debate",
    "run_debate_async",
]
