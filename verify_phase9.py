#!/usr/bin/env python3
"""Phase 9 verification harness.

This script does NOT assume success.
It prints what was demonstrated vs what is unverified and how to verify.

Usage:
  uv run python verify_phase9.py 2401.12345

Env:
  SCIJUDGE_MODELS_CONFIG=./configs/models_pluralism.example.json
  OPENAI_API_KEY=...
  ANTHROPIC_API_KEY=...
"""

import asyncio
import os
import sys
from pathlib import Path

from scientific_judgment_mcp.orchestration import run_debate_async
from scientific_judgment_mcp.reports import generate_all_artifacts
from scientific_judgment_mcp.tools.arxiv import ingest_arxiv_paper
from scientific_judgment_mcp.llm.config import ReviewModelsConfig


def _has_env(name: str) -> bool:
    val = os.environ.get(name)
    return bool(val and val.strip())


def section(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


async def main() -> int:
    section("PHASE 9.1 — MODEL PLURALISM (CONFIG + BACKENDS)")

    print(f"OPENAI_API_KEY set: {_has_env('OPENAI_API_KEY')}")
    print(f"ANTHROPIC_API_KEY set: {_has_env('ANTHROPIC_API_KEY')}")

    if not _has_env("SCIJUDGE_MODELS_CONFIG"):
        print("SCIJUDGE_MODELS_CONFIG not set -> using default per-agent config (likely all OpenAI).")
        print("To verify multi-provider disagreement, set SCIJUDGE_MODELS_CONFIG to a JSON mapping.")
        print("Example: ./configs/models_pluralism.example.json")

    models_cfg = None
    cfg_path = os.environ.get("SCIJUDGE_MODELS_CONFIG")
    if cfg_path:
        try:
            models_cfg = ReviewModelsConfig.load_from_path(Path(cfg_path))
            print(f"Loaded models config: {cfg_path}")
        except Exception as exc:
            print("UNVERIFIED: Failed to load SCIJUDGE_MODELS_CONFIG.")
            print(f"Error: {type(exc).__name__}: {exc}")
            models_cfg = None

    section("PHASE 9.3 — REAL ARXIV PAPER (NO SYNTHETIC DEMOS)")

    if len(sys.argv) < 2:
        print("UNVERIFIED: No arXiv ID provided.")
        print("Run: uv run python verify_phase9.py 2401.12345")
        return 2

    arxiv_id = sys.argv[1].strip()
    print(f"Target arXiv: {arxiv_id}")

    paper = None
    try:
        paper = await ingest_arxiv_paper(arxiv_id)
        print("✅ Ingestion succeeded")
        print(f"Title: {paper.title}")
        print(f"Authors: {', '.join(paper.authors[:8])}{'...' if len(paper.authors) > 8 else ''}")
        print(f"Heuristic claims extracted: {len(paper.claims)}")
    except Exception as exc:
        print("UNVERIFIED: arXiv ingestion failed.")
        print(f"Error: {type(exc).__name__}: {exc}")
        print("Next steps: verify network access; verify arXiv ID; check PDF download permissions.")
        return 3

    section("PHASE 9 — RUN REVIEW")

    # Build models config default from agent specs if none provided.
    if models_cfg is None:
        from scientific_judgment_mcp.agents import get_all_agent_specs
        specs = get_all_agent_specs()
        models_cfg = ReviewModelsConfig(agents={k: v.llm_config for k, v in specs.items()})

    state = await run_debate_async(paper, models_config=models_cfg)

    out_dir = Path("./reports")
    artifacts = generate_all_artifacts(state, out_dir)

    print("✅ Review completed")
    print(f"Messages: {len(state['messages'])}")
    print(f"Extraction limitations: {len(state.get('extraction_limitations', []))}")
    print(f"Model divergence items: {len(state.get('model_divergence', []))}")
    for k, p in artifacts.items():
        print(f"{k}: {p}")

    section("PHASE 9.1 — DIVERGENCE CHECK")
    if not (_has_env("OPENAI_API_KEY") and _has_env("ANTHROPIC_API_KEY")):
        print("UNVERIFIED: Multi-provider disagreement cannot be demonstrated without API keys.")
        print("Set OPENAI_API_KEY and ANTHROPIC_API_KEY, and use SCIJUDGE_MODELS_CONFIG to assign agents across providers.")
    else:
        print("Keys present: divergence capture is verifiable via the 'Model Divergence' section in the report.")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
