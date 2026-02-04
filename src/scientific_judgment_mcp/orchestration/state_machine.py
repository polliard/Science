"""Orchestration layer for multi-agent scientific deliberation.

This module implements the debate state machine using LangGraph.
"""

from enum import Enum
from typing import Annotated, TypedDict, Literal
from datetime import datetime

from pydantic import BaseModel, Field


class DebatePhase(str, Enum):
    """Phases of the scientific judgment protocol (Phase 6)."""

    INITIALIZATION = "initialization"
    CLAIM_ENUMERATION = "claim_enumeration"
    METHODOLOGICAL_REVIEW = "methodological_review"
    EVIDENCE_REVIEW = "evidence_review"
    COI_REVIEW = "coi_review"
    PROGRESS_EVALUATION = "progress_evaluation"
    DELIBERATION = "deliberation"
    VERDICT_ASSIGNMENT = "verdict_assignment"
    SYNTHESIS = "synthesis"
    COMPLETE = "complete"


class AgentRole(str, Enum):
    """Scientific Review Panel agent roles."""

    MODERATOR = "moderator"
    METHODOLOGIST = "methodologist"
    EVIDENCE_AUDITOR = "evidence_auditor"
    PARADIGM_CHALLENGER = "paradigm_challenger"
    SKEPTIC = "skeptic"
    INCENTIVES_ANALYST = "incentives_analyst"


class VerdictDimension(BaseModel):
    """Multi-axis verdict scoring."""

    methodological_soundness: int = Field(
        ge=1, le=5,
        description="Design quality, controls, execution (1-5)"
    )
    evidence_strength: int = Field(
        ge=1, le=5,
        description="Data adequacy, statistical rigor (1-5)"
    )
    novelty_value: int = Field(
        ge=1, le=5,
        description="Originality of question, method, or data (1-5)"
    )
    scientific_contribution: int = Field(
        ge=1, le=5,
        description="Usefulness to field, even if wrong (1-5)"
    )
    risk_of_overreach: int = Field(
        ge=1, le=5,
        description="Gap between data and claims (1-5)"
    )

    rationale: str = Field(
        description="Justification for scores"
    )


class AgentMessage(BaseModel):
    """Message from an agent during deliberation."""

    agent: AgentRole
    phase: DebatePhase
    timestamp: datetime = Field(default_factory=datetime.now)
    content: str
    model_provider: str | None = Field(default=None, description="LLM provider used")
    model_name: str | None = Field(default=None, description="LLM model name")
    temperature: float | None = Field(default=None, description="Sampling temperature")
    max_tokens: int | None = Field(default=None, description="Max tokens requested")
    references: list[str] = Field(
        default_factory=list,
        description="Citations to paper sections or prior messages"
    )
    flags_violation: bool = Field(
        default=False,
        description="True if agent detects principle violation"
    )


class PaperContext(BaseModel):
    """Normalized paper information for review."""

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    claims: list[str] = Field(
        default_factory=list,
        description="Enumerated claims from the paper"
    )
    methods: str = Field(
        default="",
        description="Extracted methodology section"
    )
    results: str = Field(
        default="",
        description="Extracted results section"
    )

    full_text_excerpt: str = Field(
        default="",
        description="Targeted excerpt of extracted PDF text for quote grounding (may be incomplete)"
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="Explicit or missing limitations"
    )


class DebateState(TypedDict):
    """State for the scientific judgment debate."""

    # Paper under review
    paper: PaperContext

    # Current phase
    phase: DebatePhase

    # Conversation history
    messages: Annotated[list[AgentMessage], "append-only log"]

    # Run configuration (explicit model choice per agent)
    agent_model_configs: dict[str, dict]

    # Cross-model disagreement is a signal
    model_divergence: list[dict]

    # Accumulated findings by phase
    enumerated_claims: list[str]
    methodological_findings: dict[str, str]
    evidence_findings: dict[str, str]
    coi_findings: dict[str, str]

    # Optional append-only artifacts (best-effort; may be absent)
    review_artifacts: list[dict]
    evidence_audit: dict

    # Final outputs
    verdict: VerdictDimension | None
    synthesis: str

    # Metadata
    start_time: datetime
    phase_transitions: list[tuple[DebatePhase, datetime]]

    # Audit trail
    principle_violations: list[str]

    # Extraction / tooling notes (for honesty)
    extraction_limitations: list[str]


# State transition rules
PHASE_TRANSITIONS = {
    DebatePhase.INITIALIZATION: DebatePhase.CLAIM_ENUMERATION,
    DebatePhase.CLAIM_ENUMERATION: DebatePhase.METHODOLOGICAL_REVIEW,
    DebatePhase.METHODOLOGICAL_REVIEW: DebatePhase.EVIDENCE_REVIEW,
    DebatePhase.EVIDENCE_REVIEW: DebatePhase.COI_REVIEW,
    DebatePhase.COI_REVIEW: DebatePhase.PROGRESS_EVALUATION,
    DebatePhase.PROGRESS_EVALUATION: DebatePhase.DELIBERATION,
    DebatePhase.DELIBERATION: DebatePhase.VERDICT_ASSIGNMENT,
    DebatePhase.VERDICT_ASSIGNMENT: DebatePhase.SYNTHESIS,
    DebatePhase.SYNTHESIS: DebatePhase.COMPLETE,
}


def advance_phase(current_phase: DebatePhase) -> DebatePhase:
    """Move to the next debate phase."""
    return PHASE_TRANSITIONS.get(current_phase, DebatePhase.COMPLETE)


def can_advance(state: DebateState) -> bool:
    """Check if debate can advance to next phase."""
    phase = state["phase"]

    if phase == DebatePhase.INITIALIZATION:
        return state.get("paper") is not None

    elif phase == DebatePhase.CLAIM_ENUMERATION:
        return len(state.get("enumerated_claims", [])) > 0

    elif phase == DebatePhase.METHODOLOGICAL_REVIEW:
        return len(state.get("methodological_findings", {})) > 0

    elif phase == DebatePhase.EVIDENCE_REVIEW:
        return len(state.get("evidence_findings", {})) > 0

    elif phase == DebatePhase.COI_REVIEW:
        return len(state.get("coi_findings", {})) > 0

    elif phase == DebatePhase.VERDICT_ASSIGNMENT:
        return state.get("verdict") is not None

    elif phase == DebatePhase.SYNTHESIS:
        return len(state.get("synthesis", "")) > 0

    return True


# Agent participation rules by phase
PHASE_PARTICIPANTS = {
    DebatePhase.INITIALIZATION: [AgentRole.MODERATOR],
    DebatePhase.CLAIM_ENUMERATION: [
        AgentRole.MODERATOR,
        AgentRole.EVIDENCE_AUDITOR,
        AgentRole.METHODOLOGIST,
    ],
    DebatePhase.METHODOLOGICAL_REVIEW: [
        AgentRole.MODERATOR,
        AgentRole.METHODOLOGIST,
        AgentRole.SKEPTIC,
    ],
    DebatePhase.EVIDENCE_REVIEW: [
        AgentRole.MODERATOR,
        AgentRole.EVIDENCE_AUDITOR,
        AgentRole.SKEPTIC,
        AgentRole.PARADIGM_CHALLENGER,
    ],
    DebatePhase.COI_REVIEW: [
        AgentRole.MODERATOR,
        AgentRole.INCENTIVES_ANALYST,
    ],
    DebatePhase.PROGRESS_EVALUATION: [
        AgentRole.MODERATOR,
        AgentRole.PARADIGM_CHALLENGER,
        AgentRole.EVIDENCE_AUDITOR,
    ],
    DebatePhase.DELIBERATION: [
        AgentRole.MODERATOR,
        AgentRole.METHODOLOGIST,
        AgentRole.EVIDENCE_AUDITOR,
        AgentRole.PARADIGM_CHALLENGER,
        AgentRole.SKEPTIC,
        AgentRole.INCENTIVES_ANALYST,
    ],
    DebatePhase.VERDICT_ASSIGNMENT: [
        AgentRole.MODERATOR,
    ],
    DebatePhase.SYNTHESIS: [
        AgentRole.MODERATOR,
    ],
}


def get_active_agents(phase: DebatePhase) -> list[AgentRole]:
    """Get agents that should participate in this phase."""
    return PHASE_PARTICIPANTS.get(phase, [])
