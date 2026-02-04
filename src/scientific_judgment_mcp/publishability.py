"""Publishability gate.

This module defines a canonical, deterministic mapping from the multi-axis
verdict to a single operational recommendation: publish / revise / reject.

The intent is not to collapse nuance, but to provide a consistent default
"go/no-go" style signal that remains auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from scientific_judgment_mcp.orchestration import VerdictDimension


@dataclass(frozen=True)
class PublishabilityResult:
    decision: str
    publishable: bool
    provisional: bool
    gates: dict[str, bool]
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "publishable": self.publishable,
            "provisional": self.provisional,
            "gates": dict(self.gates),
            "reasons": list(self.reasons),
        }


def _as_verdict(verdict: VerdictDimension | Mapping[str, Any]) -> VerdictDimension:
    if isinstance(verdict, VerdictDimension):
        return verdict
    return VerdictDimension.model_validate(dict(verdict))


def evaluate_publishability(
    verdict: VerdictDimension | Mapping[str, Any] | None,
    *,
    extraction_limitations: Iterable[str] | None = None,
    principle_violations: Iterable[str] | None = None,
) -> PublishabilityResult:
    """Compute the canonical publishability decision.

    Gate definition (canonical):
    - Publishable iff:
        - methodological_soundness >= 3
        - evidence_strength >= 3
        - risk_of_overreach <= 3
    - Revise/Resubmit iff:
        - methodological_soundness >= 3
        - risk_of_overreach <= 3
        - evidence_strength < 3
    - Reject otherwise.

    The result is marked provisional when tooling/extraction limitations or
    principle violations are present.
    """

    if verdict is None:
        return PublishabilityResult(
            decision="unverified",
            publishable=False,
            provisional=True,
            gates={
                "methodological_soundness>=3": False,
                "evidence_strength>=3": False,
                "risk_of_overreach<=3": False,
            },
            reasons=["No verdict present"],
        )

    v = _as_verdict(verdict)

    method_ok = v.methodological_soundness >= 3
    evidence_ok = v.evidence_strength >= 3
    overreach_ok = v.risk_of_overreach <= 3

    gates = {
        "methodological_soundness>=3": method_ok,
        "evidence_strength>=3": evidence_ok,
        "risk_of_overreach<=3": overreach_ok,
    }

    reasons: list[str] = []
    if not method_ok:
        reasons.append(f"Methodological soundness too low ({v.methodological_soundness}/5)")
    if not evidence_ok:
        reasons.append(f"Evidence strength too low ({v.evidence_strength}/5)")
    if not overreach_ok:
        reasons.append(f"Risk of overreach too high ({v.risk_of_overreach}/5)")

    if method_ok and evidence_ok and overreach_ok:
        decision = "publishable"
        publishable = True
    elif method_ok and overreach_ok and not evidence_ok:
        decision = "revise_resubmit"
        publishable = False
    else:
        decision = "reject"
        publishable = False

    extraction_limitations_list = [x for x in (extraction_limitations or []) if str(x).strip()]
    principle_violations_list = [x for x in (principle_violations or []) if str(x).strip()]
    provisional = bool(extraction_limitations_list or principle_violations_list)

    if provisional:
        if extraction_limitations_list:
            reasons.append("Provisional: extraction/tooling limitations present")
        if principle_violations_list:
            reasons.append("Provisional: principle violations were flagged")

    return PublishabilityResult(
        decision=decision,
        publishable=publishable,
        provisional=provisional,
        gates=gates,
        reasons=reasons,
    )
