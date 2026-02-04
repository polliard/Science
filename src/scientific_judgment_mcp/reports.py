"""Report generation system (Phase 7).

Produces structured markdown reports, claim tables, COI appendices,
and machine-readable JSON summaries.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from scientific_judgment_mcp.orchestration import DebateState, PaperContext, VerdictDimension
from scientific_judgment_mcp.publishability import evaluate_publishability


def generate_markdown_report(state: DebateState, output_dir: Path) -> Path:
    """Generate comprehensive markdown report of scientific review.

    Args:
        state: Final debate state
        output_dir: Directory for report output

    Returns:
        Path to generated report
    """
    paper = state["paper"]
    verdict = state["verdict"]

    report_lines = []

    # Header
    report_lines.extend([
        "# Scientific Paper Evaluation Report",
        "",
        f"**Generated**: {datetime.now().isoformat()}",
        f"**Review Duration**: {(datetime.now() - state['start_time']).total_seconds():.1f}s",
        "",
        "---",
        "",
    ])

    # Paper Information
    report_lines.extend([
        "## Paper Information",
        "",
        f"**Title**: {paper.title}",
        f"**Authors**: {', '.join(paper.authors)}",
        f"**arXiv ID**: [{paper.arxiv_id}](https://arxiv.org/abs/{paper.arxiv_id})",
        "",
        "### Abstract",
        "",
        paper.abstract,
        "",
        "---",
        "",
    ])

    # Constitutional Principles Acknowledgment
    report_lines.extend([
        "## Constitutional Principles Applied",
        "",
        "This review was conducted under the principles defined in `SCIENTIFIC_PRINCIPLES.md`:",
        "",
        "1. **Methodological Neutrality** — Non-mainstream hypotheses receive equal evaluation",
        "2. **Separation of Concerns** — Methodology ≠ Conclusions ≠ Implications",
        "3. **Anti-Orthodoxy Bias Control** — 'Contradicts consensus' triggers scrutiny, not rejection",
        "4. **COI Awareness** — Surface conflicts without guilt-by-association",
        "5. **Progress-of-Science Test** — Value contributions even when wrong",
        "",
        "---",
        "",
    ])

    # Model pluralism configuration
    model_cfgs = state.get("agent_model_configs", {})
    if model_cfgs:
        report_lines.extend([
            "## Model Configuration (Per Agent)",
            "",
            "Each agent declares its own LLM backend and sampling settings.",
            "",
            "| Agent | Provider | Model | Temp | Max tokens |",
            "|------|----------|-------|------|------------|",
        ])
        for agent_key, cfg in model_cfgs.items():
            provider = str(cfg.get("provider", ""))
            model = str(cfg.get("model", ""))
            temp = str(cfg.get("temperature", ""))
            mt = str(cfg.get("max_tokens", ""))
            report_lines.append(f"| {agent_key} | {provider} | {model} | {temp} | {mt} |")
        report_lines.extend(["", "---", ""])

    # Cross-model disagreement (signal, not error)
    divergence = state.get("model_divergence", [])
    if divergence:
        report_lines.extend([
            "## Model Divergence (Signal)",
            "",
            "The Moderator surfaces disagreements that may be model-driven.",
            "",
        ])
        for item in divergence:
            report_lines.append(f"- {item}")
        report_lines.extend(["", "---", ""])

    # Claim Enumeration
    report_lines.extend([
        "## Enumerated Claims",
        "",
        "The panel identified the following explicit claims:",
        "",
    ])

    for i, claim in enumerate(state["enumerated_claims"], 1):
        report_lines.append(f"{i}. {claim}")

    report_lines.extend(["", "---", ""])

    # Multi-Axis Verdict
    if verdict:
        pub = evaluate_publishability(
            verdict,
            extraction_limitations=state.get("extraction_limitations", []),
            principle_violations=state.get("principle_violations", []),
        )

        report_lines.extend([
            "## Multi-Axis Verdict",
            "",
            "Scientific quality is multidimensional. Scores reflect distinct aspects:",
            "",
            "| Dimension | Score | Interpretation |",
            "|-----------|-------|----------------|",
            f"| **Methodological Soundness** | {verdict.methodological_soundness}/5 | Design quality, controls, execution |",
            f"| **Evidence Strength** | {verdict.evidence_strength}/5 | Data adequacy, statistical rigor |",
            f"| **Novelty Value** | {verdict.novelty_value}/5 | Originality of question, method, or data |",
            f"| **Scientific Contribution** | {verdict.scientific_contribution}/5 | Usefulness to field, even if wrong |",
            f"| **Risk of Overreach** | {verdict.risk_of_overreach}/5 | Gap between data and claims |",
            "",
            "### Publishability Gate (Canonical)",
            "",
            f"**Decision**: {pub.decision}{" (provisional)" if pub.provisional else ""}",
            "",
            "Gates:",
            f"- methodological_soundness>=3: {pub.gates.get('methodological_soundness>=3')}",
            f"- evidence_strength>=3: {pub.gates.get('evidence_strength>=3')}",
            f"- risk_of_overreach<=3: {pub.gates.get('risk_of_overreach<=3')}",
            "",
            "Notes:",
        ])
        for reason in pub.reasons:
            report_lines.append(f"- {reason}")
        report_lines.extend([
            "### Rationale",
            "",
            verdict.rationale,
            "",
            "---",
            "",
        ])

    # Methodological Review
    report_lines.extend([
        "## Methodological Review",
        "",
        "**Scope**: Experimental design, controls, statistics (independent of conclusions)",
        "",
    ])

    for key, finding in state["methodological_findings"].items():
        report_lines.append(f"- **{key}**: {finding}")

    report_lines.extend(["", "---", ""])

    # Evidence Sufficiency
    report_lines.extend([
        "## Evidence Sufficiency",
        "",
        "**Scope**: Does data support conclusions? Are citations accurate?",
        "",
    ])

    for key, finding in state["evidence_findings"].items():
        report_lines.append(f"- **{key}**: {finding}")

    audit = state.get("evidence_audit")
    if isinstance(audit, dict) and audit:
        report_lines.extend([
            "",
            "### Evidence Audit (Quote-Grounded)",
            "",
        ])
        qv = audit.get("quote_verification") if isinstance(audit.get("quote_verification"), dict) else {}
        if isinstance(qv, dict) and qv:
            report_lines.append(
                f"- Quote grounding pass rate: {qv.get('pass_rate')} (grounded={qv.get('grounded')}, ungrounded={qv.get('ungrounded')})"
            )

        paper_type = audit.get("paper_type")
        if paper_type:
            report_lines.append(f"- Detected paper type: {paper_type}")

        prisma = audit.get("prisma_checklist")
        if isinstance(prisma, list) and prisma:
            missing = [p for p in prisma if isinstance(p, dict) and str(p.get("status") or "").lower() == "missing"]
            partial = [p for p in prisma if isinstance(p, dict) and str(p.get("status") or "").lower() == "partial"]
            report_lines.append(f"- PRISMA checklist: missing={len(missing)}, partial={len(partial)}, total={len(prisma)}")
            for p in (missing[:5] + partial[:3]):
                item = (p or {}).get("item")
                st = (p or {}).get("status")
                if item:
                    report_lines.append(f"  - {st}: {item}")

    report_lines.extend(["", "---", ""])

    # Conflicts of Interest (Appendix)
    report_lines.extend([
        "## Appendix A: Conflicts of Interest Analysis",
        "",
        "**CRITICAL**: This section provides INFORMATION, not DISQUALIFICATION.",
        "",
        "Presence of conflicts does not invalidate work; absence does not validate it.",
        "",
    ])

    for key, finding in state["coi_findings"].items():
        report_lines.append(f"### {key.replace('_', ' ').title()}")
        report_lines.append("")
        report_lines.append(finding)
        report_lines.append("")

    report_lines.extend(["---", ""])

    # Chair's Synthesis
    report_lines.extend([
        "## Chair's Synthesis",
        "",
        state.get("synthesis", "Synthesis pending"),
        "",
        "---",
        "",
    ])

    # Principle Violations (if any)
    if state.get("principle_violations"):
        report_lines.extend([
            "## ⚠️ Principle Violations Detected",
            "",
            "The following violations of constitutional principles were flagged:",
            "",
        ])

        for violation in state["principle_violations"]:
            report_lines.append(f"- {violation}")

        report_lines.extend(["", "---", ""])

    # Limitations & Uncertainty
    report_lines.extend([
        "## Limitations of This Review",
        "",
        "This review has the following limitations:",
        "",
        "- **No access to raw data** — Could not verify data directly",
        "- **PDF extraction limitations** — Text extraction may be incomplete",
        "- **Limited author research** — COI analysis may be incomplete",
        "- **Single review** — No independent replication of evaluation",
        "",
    ])

    extra_limits = state.get("extraction_limitations", [])
    if extra_limits:
        report_lines.extend([
            "### Extraction / Tooling Limitations (Run-Specific)",
            "",
        ])
        for lim in extra_limits:
            report_lines.append(f"- {lim}")

    report_lines.extend([
        "### Uncertainty Acknowledgment",
        "",
        "This review provides structured analysis, not definitive truth.",
        "",
        "Areas of uncertainty:",
        "- Whether all relevant alternative explanations were considered",
        "- Whether cited literature was fully representative",
        "- Whether subtle methodological issues were detected",
        "",
        "**'We don't know' is a valid conclusion.**",
        "",
        "---",
        "",
    ])

    # Audit Trail
    report_lines.extend([
        "## Appendix B: Audit Trail",
        "",
        "### Phase Transitions",
        "",
    ])

    for phase, timestamp in state["phase_transitions"]:
        report_lines.append(f"- **{phase.value}**: {timestamp.isoformat()}")

    report_lines.extend([
        "",
        f"### Total Messages: {len(state['messages'])}",
        "",
        "---",
        "",
    ])

    # Footer
    report_lines.extend([
        "## System Information",
        "",
        "**System**: Scientific Paper Judgment System v0.1.0",
        "**Principles**: SCIENTIFIC_PRINCIPLES.md",
        "**Orchestration**: LangGraph multi-agent deliberation",
        "**Agents**: Moderator, Methodologist, Evidence Auditor, Paradigm Challenger, Skeptic, Incentives Analyst",
        "",
        "---",
        "",
        "*This is a scientific instrument. Treat it as such.*",
    ])

    # Write report
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"review_{paper.arxiv_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    report_path.write_text("\n".join(report_lines))

    return report_path


def generate_claim_table(state: DebateState, output_dir: Path) -> Path:
    """Generate claim-by-claim evaluation table.

    Args:
        state: Final debate state
        output_dir: Directory for output

    Returns:
        Path to generated table
    """
    paper = state["paper"]

    lines = [
        "# Claim-by-Claim Evaluation",
        "",
        f"**Paper**: {paper.title}",
        f"**arXiv ID**: {paper.arxiv_id}",
        "",
        "| # | Claim | Methodology | Evidence | Notes |",
        "|---|-------|-------------|----------|-------|",
    ]

    for i, claim in enumerate(state["enumerated_claims"], 1):
        # In real implementation, would have per-claim evaluations
        lines.append(f"| {i} | {claim[:50]}... | TBD | TBD | TBD |")

    output_dir.mkdir(parents=True, exist_ok=True)
    table_path = output_dir / f"claims_{paper.arxiv_id}.md"

    table_path.write_text("\n".join(lines))

    return table_path


def generate_json_summary(state: DebateState, output_dir: Path) -> Path:
    """Generate machine-readable JSON summary.

    Args:
        state: Final debate state
        output_dir: Directory for output

    Returns:
        Path to generated JSON
    """
    import json

    paper = state["paper"]
    verdict = state["verdict"]

    summary = {
        "paper": {
            "arxiv_id": paper.arxiv_id,
            "title": paper.title,
            "authors": paper.authors,
        },
        "verdict": verdict.model_dump() if verdict else None,
        "publishability": evaluate_publishability(
            verdict,
            extraction_limitations=state.get("extraction_limitations", []),
            principle_violations=state.get("principle_violations", []),
        ).to_dict()
        if verdict
        else None,
        "review_metadata": {
            "start_time": state["start_time"].isoformat(),
            "phases_completed": len(state["phase_transitions"]),
            "total_messages": len(state["messages"]),
            "principle_violations": len(state.get("principle_violations", [])),
        },
        "claims": state["enumerated_claims"],
        "methodological_findings": state["methodological_findings"],
        "evidence_findings": state["evidence_findings"],
        "coi_findings": state["coi_findings"],
        "synthesis": state.get("synthesis", ""),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"summary_{paper.arxiv_id}.json"

    json_path.write_text(json.dumps(summary, indent=2))

    return json_path


def generate_all_artifacts(state: DebateState, output_dir: Optional[Path] = None) -> dict[str, Path]:
    """Generate all output artifacts.

    Args:
        state: Final debate state
        output_dir: Optional output directory (default: ./reports)

    Returns:
        Dictionary mapping artifact type to path
    """
    if output_dir is None:
        output_dir = Path("./reports")

    artifacts = {
        "markdown_report": generate_markdown_report(state, output_dir),
        "claim_table": generate_claim_table(state, output_dir),
        "json_summary": generate_json_summary(state, output_dir),
    }

    return artifacts
