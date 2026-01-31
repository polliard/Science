"""Human feedback loop (Phase 9.6).

This module intentionally does NOT overwrite history.
It classifies feedback and produces forward-looking change notes.
"""

from __future__ import annotations

from typing import Any


CATEGORIES = {
    "methodology": ["method", "control", "random", "blind", "statistics", "power", "confound"],
    "evidence": ["evidence", "data", "sample", "result", "figure", "supports", "insufficient"],
    "overreach": ["overreach", "exagger", "claim", "conclude", "speculat"],
    "incentives": ["fund", "grant", "industry", "conflict", "coi", "incentive", "affiliation"],
    "progress": ["prediction", "testable", "useful", "contribution", "progress"],
}


def classify_human_critique(text: str) -> dict[str, Any]:
    """Heuristic classifier.

    Returns categories + matched keywords.
    This is intentionally conservative and can be replaced by an LLM-assisted classifier later.
    """

    lower = text.lower()
    hits: dict[str, list[str]] = {}
    for cat, kws in CATEGORIES.items():
        matched = [kw for kw in kws if kw in lower]
        if matched:
            hits[cat] = matched

    return {
        "categories": sorted(hits.keys()),
        "matches": hits,
        "note": "Heuristic classification (UNVERIFIED); replace with LLM classifier if desired.",
    }


def compare_feedback_to_review(*, critique: dict[str, Any], review_state: dict[str, Any]) -> dict[str, Any]:
    """Compare critique categories against what agents discussed.

    This is a simple audit: if a category appears in critique but not in the transcript,
    we flag it as a potential blind spot.
    """

    critique_cats = set(critique.get("categories", []))

    transcript = "\n".join(
        [
            f"{m.get('phase')}::{m.get('agent')}: {m.get('content','')}"
            for m in (review_state.get("agent_messages") or [])
        ]
    ).lower()

    missing = []
    for cat in sorted(critique_cats):
        if cat not in transcript:
            missing.append(cat)

    return {
        "critique_categories": sorted(critique_cats),
        "potential_blind_spots": missing,
        "note": "String-match comparison (UNVERIFIED) — does not prove absence of consideration.",
    }


def propose_forward_change(*, comparison: dict[str, Any]) -> str:
    """Generate a forward-looking change note without rewriting history."""

    missing = comparison.get("potential_blind_spots", [])
    if not missing:
        return "No prompt/weighting changes proposed; critique overlaps existing coverage."

    return (
        "Going forward: increase explicit attention to these critique categories during deliberation: "
        + ", ".join(missing)
        + ". Past verdicts remain unchanged; this is a forward-only adjustment note."
    )
