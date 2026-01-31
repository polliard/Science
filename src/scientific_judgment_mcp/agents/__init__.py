"""Agent definitions for the Scientific Review Panel."""

from .specifications import (
    AgentSpec,
    MODERATOR_SPEC,
    METHODOLOGIST_SPEC,
    EVIDENCE_AUDITOR_SPEC,
    PARADIGM_CHALLENGER_SPEC,
    SKEPTIC_SPEC,
    INCENTIVES_ANALYST_SPEC,
    AGENT_SPECS,
    get_agent_spec,
    get_all_agent_specs,
)

__all__ = [
    "AgentSpec",
    "MODERATOR_SPEC",
    "METHODOLOGIST_SPEC",
    "EVIDENCE_AUDITOR_SPEC",
    "PARADIGM_CHALLENGER_SPEC",
    "SKEPTIC_SPEC",
    "INCENTIVES_ANALYST_SPEC",
    "AGENT_SPECS",
    "get_agent_spec",
    "get_all_agent_specs",
]
