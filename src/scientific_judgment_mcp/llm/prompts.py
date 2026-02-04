"""Prompt templates.

We avoid hidden chain-of-thought and ask for concise, checkable outputs.
"""

from __future__ import annotations


SYSTEM_NO_COT = (
    "You are an expert scientific reviewer. "
    "Do NOT provide hidden chain-of-thought. "
    "Provide conclusions and short, checkable justifications only. "
    "If uncertain, say so explicitly."
)


def build_phase_prompt(*, phase_name: str, role_name: str, instructions: str, paper_context: str) -> str:
    return (
        f"ROLE: {role_name}\n"
        f"PHASE: {phase_name}\n\n"
        "CONSTRAINTS:\n"
        "- No consensus-as-evidence\n"
        "- No guilt-by-association\n"
        "- Separate methods vs evidence vs implications\n"
        "- Label uncertainty; do not bluff\n\n"
        f"TASK:\n{instructions}\n\n"
        f"PAPER CONTEXT:\n{paper_context}\n"
    )


def render_paper_context_for_llm(*, title: str, authors: list[str], arxiv_id: str, abstract: str, claims: list[str], methods: str, results: str) -> str:
    claims_block = "\n".join([f"- {c}" for c in claims]) if claims else "(none extracted yet)"
    methods_snip = methods.strip()[:6000] if methods else "(methods section not reliably extracted)"
    results_snip = results.strip()[:6000] if results else "(results section not reliably extracted)"

    return (
        f"Title: {title}\n"
        f"Authors: {', '.join(authors)}\n"
        f"arXiv: {arxiv_id}\n\n"
        "Abstract:\n"
        f"{abstract}\n\n"
        "Extracted Claims (may be incomplete):\n"
        f"{claims_block}\n\n"
        "Extracted Methods (may be incomplete):\n"
        f"{methods_snip}\n\n"
        "Extracted Results (may be incomplete):\n"
        f"{results_snip}\n"
    )


def render_paper_context_for_llm_with_excerpt(
    *,
    title: str,
    authors: list[str],
    arxiv_id: str,
    abstract: str,
    claims: list[str],
    methods: str,
    results: str,
    full_text_excerpt: str,
) -> str:
    base = render_paper_context_for_llm(
        title=title,
        authors=authors,
        arxiv_id=arxiv_id,
        abstract=abstract,
        claims=claims,
        methods=methods,
        results=results,
    )
    excerpt = (full_text_excerpt or "").strip()
    if not excerpt:
        return base

    excerpt_snip = excerpt[:18000]
    return base + (
        "\n\nFull Text Excerpt for Quote Grounding (may be incomplete):\n"
        f"{excerpt_snip}\n"
    )
