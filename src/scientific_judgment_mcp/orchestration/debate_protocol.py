"""Debate protocol implementation using LangGraph.

Phase 9.1: This module now supports real multi-agent deliberation driven by
multiple LLM backends (per-agent explicit model choice).
"""

import asyncio
import json
from typing import Any, Callable
from datetime import datetime

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state_machine import (
    DebateState,
    DebatePhase,
    AgentRole,
    AgentMessage,
    advance_phase,
    can_advance,
    get_active_agents,
    PaperContext,
)

from scientific_judgment_mcp.agents import get_all_agent_specs
from scientific_judgment_mcp.llm.runner import AgentRunner
from scientific_judgment_mcp.llm.config import ReviewModelsConfig, load_models_config_from_env
from scientific_judgment_mcp.llm.prompts import build_phase_prompt, render_paper_context_for_llm


# Progress callbacks are a best-effort mechanism for UIs.
# Keyed by LangGraph thread_id (which may differ from arXiv id in web runs).
ProgressCallback = Callable[[AgentMessage, DebateState], None]
_PROGRESS_CALLBACKS: dict[str, ProgressCallback] = {}


def register_progress_callback(thread_id: str, cb: ProgressCallback) -> None:
    _PROGRESS_CALLBACKS[thread_id] = cb


def unregister_progress_callback(thread_id: str) -> None:
    _PROGRESS_CALLBACKS.pop(thread_id, None)


def create_debate_graph() -> StateGraph:
    """Create the LangGraph state machine for scientific debate.

    This implements the 6-step judgment protocol from Phase 6:
    1. Claim Enumeration
    2. Methodological Review
    3. Evidence Sufficiency Review
    4. Incentives & COI Review
    5. Progress-of-Science Evaluation
    6. Verdict Assignment (Multi-Axis)
    """

    # Initialize graph with debate state
    workflow = StateGraph(DebateState)

    # Define nodes (one per phase)
    workflow.add_node("initialize", initialize_debate)
    workflow.add_node("enumerate_claims", enumerate_claims)
    workflow.add_node("review_methodology", review_methodology)
    workflow.add_node("review_evidence", review_evidence)
    workflow.add_node("review_coi", review_coi)
    workflow.add_node("evaluate_progress", evaluate_progress)
    workflow.add_node("deliberate", deliberate)
    workflow.add_node("assign_verdict", assign_verdict)
    workflow.add_node("synthesize", synthesize)

    # Define edges (phase transitions)
    workflow.set_entry_point("initialize")

    workflow.add_edge("initialize", "enumerate_claims")
    workflow.add_edge("enumerate_claims", "review_methodology")
    workflow.add_edge("review_methodology", "review_evidence")
    workflow.add_edge("review_evidence", "review_coi")
    workflow.add_edge("review_coi", "evaluate_progress")
    workflow.add_edge("evaluate_progress", "deliberate")
    workflow.add_edge("deliberate", "assign_verdict")
    workflow.add_edge("assign_verdict", "synthesize")
    workflow.add_edge("synthesize", END)

    return workflow


def _default_models_config() -> ReviewModelsConfig:
    specs = get_all_agent_specs()
    return ReviewModelsConfig(
        agents={k: v.llm_config for k, v in specs.items()}
    )


def _paper_context_text(paper: PaperContext) -> str:
    return render_paper_context_for_llm(
        title=paper.title,
        authors=paper.authors,
        arxiv_id=paper.arxiv_id,
        abstract=paper.abstract,
        claims=paper.claims,
        methods=paper.methods,
        results=paper.results,
    )


def _append_agent_message(
    state: DebateState,
    *,
    agent_role: AgentRole,
    phase: DebatePhase,
    content: str,
    model: dict[str, Any] | None,
) -> None:
    msg = AgentMessage(
        agent=agent_role,
        phase=phase,
        content=content,
        model_provider=(model or {}).get("provider"),
        model_name=(model or {}).get("model"),
        temperature=(model or {}).get("temperature"),
        max_tokens=(model or {}).get("max_tokens"),
    )
    state["messages"].append(msg)

    try:
        tid = state.get("_thread_id") or state["paper"].arxiv_id
        cb = _PROGRESS_CALLBACKS.get(str(tid))
        if cb is not None:
            cb(msg, state)
    except Exception:
        # Progress callbacks must never break the core review pipeline.
        pass


def _get_model_cfg(state: DebateState, role_key: str) -> dict[str, Any]:
    return state["agent_model_configs"].get(role_key, {})


def _run_agent_json(
    *,
    runner: AgentRunner,
    agent_key: str,
    phase: DebatePhase,
    instructions: str,
    paper_text: str,
    state: DebateState,
) -> dict[str, Any] | None:
    specs = get_all_agent_specs()
    spec = specs[agent_key]

    model_cfg = spec.llm_config
    override = state["agent_model_configs"].get(agent_key)
    if override:
        # preserve pydantic validation by reconstructing
        model_cfg = type(model_cfg).model_validate(override)

    prompt = build_phase_prompt(
        phase_name=phase.value,
        role_name=spec.role,
        instructions=instructions,
        paper_context=paper_text,
    )

    result = runner.run_json(agent=spec, model_cfg=model_cfg, user_prompt=prompt)
    _append_agent_message(
        state,
        agent_role=AgentRole(agent_key),
        phase=phase,
        content=result.content,
        model={
            "provider": result.model.provider,
            "model": result.model.model,
            "temperature": result.model.temperature,
            "max_tokens": result.model.max_tokens,
        },
    )
    return result.raw


# ============================================================================
# NODE IMPLEMENTATIONS (Phase-specific logic)
# ============================================================================


def initialize_debate(state: DebateState) -> DebateState:
    """Initialize debate with paper context.

    Moderator: Sets stage, reviews principles, prepares agents.
    """
    state["phase"] = DebatePhase.INITIALIZATION
    state["start_time"] = datetime.now()
    state["phase_transitions"] = [(DebatePhase.INITIALIZATION, datetime.now())]
    state.setdefault("agent_model_configs", {})
    state.setdefault("model_divergence", [])
    state.setdefault("extraction_limitations", [])

    # Carry forward any ingestion-time limitations (e.g., PDF parsing issues, insecure TLS).
    try:
        state["extraction_limitations"].extend(state["paper"].limitations)
    except Exception:
        pass

    # Moderator message
    moderator_message = AgentMessage(
        agent=AgentRole.MODERATOR,
        phase=DebatePhase.INITIALIZATION,
        content=f"""Scientific Review Panel convened.

Paper: {state['paper'].title}
Authors: {', '.join(state['paper'].authors)}
arXiv ID: {state['paper'].arxiv_id}

Constitutional Principles Active:
1. Methodological Neutrality
2. Separation of Concerns
3. Anti-Orthodoxy Bias Control
4. COI Awareness (not dismissal)
5. Progress-of-Science Test

All agents: Review SCIENTIFIC_PRINCIPLES.md.
Paradigm Challenger: You are explicitly tasked with defending
the RIGHT of non-mainstream ideas to exist and be evaluated fairly.

We proceed in phases. No shortcuts. No consensus-as-evidence.
""",
    )

    state["messages"] = [moderator_message]

    return state


def enumerate_claims(state: DebateState) -> DebateState:
    """Phase 1: Enumerate claims from the paper.

    Participants: Moderator, Evidence Auditor, Methodologist

    Goal: List explicit claims the paper makes, without judgment.
    """
    state["phase"] = DebatePhase.CLAIM_ENUMERATION
    state["phase_transitions"].append((DebatePhase.CLAIM_ENUMERATION, datetime.now()))

    runner = AgentRunner()
    paper_text = _paper_context_text(state["paper"])

    _append_agent_message(
        state,
        agent_role=AgentRole.MODERATOR,
        phase=DebatePhase.CLAIM_ENUMERATION,
        content="Phase 1: Enumerate explicit claims (no judgment).",
        model=None,
    )

    instructions = (
        "Extract the paper's explicit claims. Do not evaluate truth. "
        "Return JSON: {\"claims\": [..], \"extraction_limitations\": [..]}"
    )

    claims_raw = _run_agent_json(
        runner=runner,
        agent_key=AgentRole.EVIDENCE_AUDITOR.value,
        phase=DebatePhase.CLAIM_ENUMERATION,
        instructions=instructions,
        paper_text=paper_text,
        state=state,
    )

    claims = None
    if claims_raw and isinstance(claims_raw.get("claims"), list):
        claims = [str(c).strip() for c in claims_raw["claims"] if str(c).strip()]
        lim = claims_raw.get("extraction_limitations")
        if isinstance(lim, list):
            state["extraction_limitations"].extend([str(x) for x in lim])

    if not claims:
        # fall back to heuristic extraction already in PaperContext
        claims = state["paper"].claims or [state["paper"].abstract]
        state["extraction_limitations"].append(
            "Claim extraction JSON parse failed; fell back to heuristic claims from abstract."
        )

    state["enumerated_claims"] = claims

    return state


def review_methodology(state: DebateState) -> DebateState:
    """Phase 2: Methodological Review.

    Participants: Moderator, Methodologist, Skeptic

    Goal: Evaluate experimental design, controls, statistics.
    Must NOT evaluate truth of conclusions—only appropriateness of methods.
    """
    state["phase"] = DebatePhase.METHODOLOGICAL_REVIEW
    state["phase_transitions"].append((DebatePhase.METHODOLOGICAL_REVIEW, datetime.now()))

    runner = AgentRunner()
    paper_text = _paper_context_text(state["paper"])

    _append_agent_message(
        state,
        agent_role=AgentRole.MODERATOR,
        phase=DebatePhase.METHODOLOGICAL_REVIEW,
        content="Phase 2: Evaluate methodology only (methods ≠ truth).",
        model=None,
    )

    instructions = (
        "Evaluate experimental design, controls, statistics, reproducibility. "
        "Return JSON: {\"findings\": {\"key\": \"finding\"}, \"extraction_limitations\": [..]}"
    )

    meth_raw = _run_agent_json(
        runner=runner,
        agent_key=AgentRole.METHODOLOGIST.value,
        phase=DebatePhase.METHODOLOGICAL_REVIEW,
        instructions=instructions,
        paper_text=paper_text,
        state=state,
    )

    findings: dict[str, str] = {}
    if meth_raw and isinstance(meth_raw.get("findings"), dict):
        findings.update({str(k): str(v) for k, v in meth_raw["findings"].items()})
        lim = meth_raw.get("extraction_limitations")
        if isinstance(lim, list):
            state["extraction_limitations"].extend([str(x) for x in lim])

    if not findings:
        findings = {"note": "Methodology review unavailable (LLM JSON parse failed)."}
        state["extraction_limitations"].append(
            "Methodology JSON parse failed; findings may be incomplete."
        )

    state["methodological_findings"] = findings

    return state


def review_evidence(state: DebateState) -> DebateState:
    """Phase 3: Evidence Sufficiency Review.

    Participants: Moderator, Evidence Auditor, Skeptic, Paradigm Challenger

    Goal: Does the data support the conclusions drawn?
    Paradigm Challenger ensures non-mainstream ideas aren't dismissed unfairly.
    """
    state["phase"] = DebatePhase.EVIDENCE_REVIEW
    state["phase_transitions"].append((DebatePhase.EVIDENCE_REVIEW, datetime.now()))

    runner = AgentRunner()
    paper_text = _paper_context_text(state["paper"])

    _append_agent_message(
        state,
        agent_role=AgentRole.MODERATOR,
        phase=DebatePhase.EVIDENCE_REVIEW,
        content="Phase 3: Does evidence support claims? Include alternatives and parity checks.",
        model=None,
    )

    instructions = (
        "Assess whether the results support the enumerated claims; identify gaps and alternative explanations. "
        "Return JSON: {\"findings\": {\"key\": \"finding\"}, \"overall\": \"...\", \"extraction_limitations\": [..]}"
    )

    ev_raw = _run_agent_json(
        runner=runner,
        agent_key=AgentRole.EVIDENCE_AUDITOR.value,
        phase=DebatePhase.EVIDENCE_REVIEW,
        instructions=instructions,
        paper_text=paper_text,
        state=state,
    )

    findings: dict[str, str] = {}
    if ev_raw and isinstance(ev_raw.get("findings"), dict):
        findings.update({str(k): str(v) for k, v in ev_raw["findings"].items()})
    if ev_raw and isinstance(ev_raw.get("overall"), str):
        findings.setdefault("overall", ev_raw["overall"])
    lim = ev_raw.get("extraction_limitations") if ev_raw else None
    if isinstance(lim, list):
        state["extraction_limitations"].extend([str(x) for x in lim])

    if not findings:
        findings = {"note": "Evidence review unavailable (LLM JSON parse failed)."}
        state["extraction_limitations"].append(
            "Evidence JSON parse failed; findings may be incomplete."
        )

    state["evidence_findings"] = findings

    return state


def review_coi(state: DebateState) -> DebateState:
    """Phase 4: Incentives & Conflict of Interest Review.

    Participants: Moderator, Incentives Analyst

    Goal: Surface conflicts WITHOUT using them to dismiss.
    """
    state["phase"] = DebatePhase.COI_REVIEW
    state["phase_transitions"].append((DebatePhase.COI_REVIEW, datetime.now()))

    _append_agent_message(
        state,
        agent_role=AgentRole.MODERATOR,
        phase=DebatePhase.COI_REVIEW,
        content="Phase 4: Surface COI/incentives as facts, not dismissal.",
        model=None,
    )

    # Phase 9.2 will enrich this tool output; for now call existing stub.
    from scientific_judgment_mcp.tools.author_research import analyze_conflicts_of_interest

    try:
        report = asyncio.run(
            analyze_conflicts_of_interest(
                authors=state["paper"].authors,
                paper_title=state["paper"].title,
                paper_metadata={"arxiv_id": state["paper"].arxiv_id},
            )
        )
        state["coi_findings"] = {
            "coi_report": json.dumps(report.model_dump(mode="json"), indent=2)
        }
    except RuntimeError:
        # If already in an event loop, do a best-effort sync fallback.
        state["coi_findings"] = {
            "coi_report": "COI enrichment not executed (event loop constraint)."
        }
        state["extraction_limitations"].append(
            "COI tool not executed due to event loop constraint."
        )

    return state


def evaluate_progress(state: DebateState) -> DebateState:
    """Phase 5: Progress-of-Science Evaluation.

    Participants: Moderator, Paradigm Challenger, Evidence Auditor

    Goal: Does this move inquiry forward, even if wrong?
    """
    state["phase"] = DebatePhase.PROGRESS_EVALUATION
    state["phase_transitions"].append((DebatePhase.PROGRESS_EVALUATION, datetime.now()))

    runner = AgentRunner()
    paper_text = _paper_context_text(state["paper"])

    _append_agent_message(
        state,
        agent_role=AgentRole.MODERATOR,
        phase=DebatePhase.PROGRESS_EVALUATION,
        content="Phase 5: Evaluate progress-of-science value (even if wrong).",
        model=None,
    )

    instructions = (
        "Evaluate progress-of-science value: testable predictions, useful methods/data, framing, and future work. "
        "Return JSON: {\"findings\": {\"key\": \"finding\"}}"
    )

    prog_raw = _run_agent_json(
        runner=runner,
        agent_key=AgentRole.PARADIGM_CHALLENGER.value,
        phase=DebatePhase.PROGRESS_EVALUATION,
        instructions=instructions,
        paper_text=paper_text,
        state=state,
    )

    if prog_raw and isinstance(prog_raw.get("findings"), dict):
        for k, v in prog_raw["findings"].items():
            state["evidence_findings"].setdefault(f"progress::{k}", str(v))

    return state


def deliberate(state: DebateState) -> DebateState:
    """Open deliberation among all agents.

    Participants: All agents

    Moderator prevents pile-ons and ensures Paradigm Challenger is heard.
    """
    state["phase"] = DebatePhase.DELIBERATION
    state["phase_transitions"].append((DebatePhase.DELIBERATION, datetime.now()))

    runner = AgentRunner()
    paper_text = _paper_context_text(state["paper"])

    instructions = (
        "Briefly summarize your key concerns or defenses, and name 1-3 points where you expect other agents to disagree. "
        "Return JSON: {\"summary\": \"...\", \"anticipated_disagreements\": [..]}"
    )

    for role in get_active_agents(DebatePhase.DELIBERATION):
        _run_agent_json(
            runner=runner,
            agent_key=role.value,
            phase=DebatePhase.DELIBERATION,
            instructions=instructions,
            paper_text=paper_text,
            state=state,
        )

    return state

    return state


def assign_verdict(state: DebateState) -> DebateState:
    """Phase 6: Assign Multi-Axis Verdict.

    Participants: Moderator (with agent input)

    Scores 5 dimensions, not binary accept/reject.
    """
    state["phase"] = DebatePhase.VERDICT_ASSIGNMENT
    state["phase_transitions"].append((DebatePhase.VERDICT_ASSIGNMENT, datetime.now()))

    moderator_msg = AgentMessage(
        agent=AgentRole.MODERATOR,
        phase=DebatePhase.VERDICT_ASSIGNMENT,
        content="""Verdict Assignment

I will now synthesize agent input into multi-axis scores.
Agents: Provide your dimensional assessments.""",
    )
    state["messages"].append(moderator_msg)

    runner = AgentRunner()

    paper_text = _paper_context_text(state["paper"])
    context = {
        "claims": state.get("enumerated_claims", []),
        "methodology": state.get("methodological_findings", {}),
        "evidence": state.get("evidence_findings", {}),
        "coi": state.get("coi_findings", {}),
        "limitations": state.get("extraction_limitations", []),
    }

    instructions = (
        "Assign multi-axis scores (1-5) and rationale. "
        "Return JSON: {"
        "\"methodological_soundness\": int, \"evidence_strength\": int, \"novelty_value\": int, "
        "\"scientific_contribution\": int, \"risk_of_overreach\": int, \"rationale\": str}"
        "\nUse only the provided context; acknowledge uncertainties."
        f"\n\nCONTEXT JSON:\n{json.dumps(context, indent=2)}"
    )

    verdict_raw = _run_agent_json(
        runner=runner,
        agent_key=AgentRole.MODERATOR.value,
        phase=DebatePhase.VERDICT_ASSIGNMENT,
        instructions=instructions,
        paper_text=paper_text,
        state=state,
    )

    from .state_machine import VerdictDimension

    try:
        if verdict_raw is None:
            raise ValueError("no verdict json")
        state["verdict"] = VerdictDimension.model_validate(verdict_raw)
    except Exception:
        state["verdict"] = VerdictDimension(
            methodological_soundness=3,
            evidence_strength=3,
            novelty_value=3,
            scientific_contribution=3,
            risk_of_overreach=3,
            rationale="Verdict JSON parse failed; placeholder scores used.",
        )
        state["extraction_limitations"].append(
            "Verdict JSON parse failed; placeholder verdict used."
        )

    return state


def synthesize(state: DebateState) -> DebateState:
    """Final synthesis by Moderator.

    Produces the chair's report with:
    - Summary
    - Minority opinions
    - Limitations of review
    - Uncertainty acknowledgment
    """
    state["phase"] = DebatePhase.SYNTHESIS
    state["phase_transitions"].append((DebatePhase.SYNTHESIS, datetime.now()))

    runner = AgentRunner()
    paper_text = _paper_context_text(state["paper"])

    # Provide transcript summary to Moderator for divergence surfacing.
    transcript = []
    for msg in state["messages"]:
        ident = ""
        if msg.model_provider and msg.model_name:
            ident = f" ({msg.model_provider}:{msg.model_name})"
        transcript.append(f"[{msg.phase.value}] {msg.agent.value}{ident}: {msg.content}")
    transcript_text = "\n\n".join(transcript[-50:])

    instructions = (
        "Write the Chair synthesis. Requirements: "
        "(1) summarize claims and evidence boundaries, "
        "(2) surface disagreements, explicitly noting if divergence appears model-driven, "
        "(3) document dissenting opinions, "
        "(4) list extraction/tooling limitations, "
        "(5) do not dismiss for non-mainstream positions. "
        "Return plain text (not JSON)."
        f"\n\nTRANSCRIPT (last ~50 messages):\n{transcript_text}"
    )

    specs = get_all_agent_specs()
    moderator = specs[AgentRole.MODERATOR.value]
    result = runner.run_text(agent=moderator, model_cfg=moderator.llm_config, user_prompt=build_phase_prompt(
        phase_name=DebatePhase.SYNTHESIS.value,
        role_name=moderator.role,
        instructions=instructions,
        paper_context=paper_text,
    ))

    # Structured divergence extraction (best-effort).
    divergence_prompt = (
        "Extract cross-agent disagreements that might be model-driven. "
        "Return STRICT JSON: {\"divergence\": [\"...\", ...]}. "
        "If none, return {\"divergence\": []}."
        f"\n\nTRANSCRIPT:\n{transcript_text}"
    )
    div = runner.run_json(
        agent=moderator,
        model_cfg=moderator.llm_config,
        user_prompt=build_phase_prompt(
            phase_name="divergence_extraction",
            role_name=moderator.role,
            instructions=divergence_prompt,
            paper_context=paper_text,
        ),
    )
    if div.raw and isinstance(div.raw.get("divergence"), list):
        state["model_divergence"] = [str(x) for x in div.raw["divergence"]]

    _append_agent_message(
        state,
        agent_role=AgentRole.MODERATOR,
        phase=DebatePhase.SYNTHESIS,
        content=result.content,
        model={
            "provider": result.model.provider,
            "model": result.model.model,
            "temperature": result.model.temperature,
            "max_tokens": result.model.max_tokens,
        },
    )

    state["synthesis"] = result.content
    state["phase"] = DebatePhase.COMPLETE

    return state


# ============================================================================
# EXECUTION
# ============================================================================


async def run_debate_async(
    paper: PaperContext,
    models_config: ReviewModelsConfig | None = None,
    *,
    thread_id: str | None = None,
) -> DebateState:
    """Execute the full scientific judgment debate for a paper.

    Args:
        paper: Normalized paper context from arXiv ingestion

    Returns:
        Complete debate state with verdict and synthesis
    """

    # Create graph
    workflow = create_debate_graph()

    # Compile with checkpointing for auditability
    checkpointer = MemorySaver()
    app = workflow.compile(checkpointer=checkpointer)

    if models_config is None:
        models_config = load_models_config_from_env(_default_models_config())

    # Initial state
    tid = thread_id or paper.arxiv_id
    initial_state: DebateState = {
        "paper": paper,
        "_thread_id": tid,
        "phase": DebatePhase.INITIALIZATION,
        "messages": [],
        "agent_model_configs": {k: v.model_dump() for k, v in models_config.agents.items()},
        "model_divergence": [],
        "enumerated_claims": [],
        "methodological_findings": {},
        "evidence_findings": {},
        "coi_findings": {},
        "verdict": None,
        "synthesis": "",
        "start_time": datetime.now(),
        "phase_transitions": [],
        "principle_violations": [],
        "extraction_limitations": [],
    }

    # Run the graph
    config = {"configurable": {"thread_id": tid}}
    final_state = await app.ainvoke(initial_state, config)

    return final_state


def run_debate(
    paper: PaperContext,
    models_config: ReviewModelsConfig | None = None,
    *,
    thread_id: str | None = None,
) -> DebateState:
    """Sync wrapper for CLI usage."""

    return asyncio.run(run_debate_async(paper, models_config=models_config, thread_id=thread_id))
