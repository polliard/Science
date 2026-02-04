#!/usr/bin/env python3
"""Phase 9.4 Supabase persistence verification.

This script is conservative:
- It will NOT print secrets.
- It will report permission/schema issues explicitly.

Prereqs:
- Run supabase/schema.sql in Supabase SQL editor
- Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (preferred) or SUPABASE_API_KEY

Usage:
  uv run python verify_supabase.py
"""

from __future__ import annotations

import asyncio

from scientific_judgment_mcp.persistence import get_supabase_client, ReviewsRepository
from scientific_judgment_mcp.orchestration import PaperContext, run_debate_async


async def main() -> int:
    try:
        client = get_supabase_client(env_path=".env")
    except Exception as exc:
        print("UNVERIFIED: Supabase client not configured.")
        print(f"Error: {type(exc).__name__}: {exc}")
        return 2

    repo = ReviewsRepository(client)

    # Minimal mock run to store.
    paper = PaperContext(
        arxiv_id="2401.00001",
        title="Supabase Persistence Smoke Test",
        authors=["Alice Researcher"],
        abstract="This is a test payload for persistence.",
        claims=["Test claim"],
        methods="",
        results="",
        limitations=[],
    )

    state = await run_debate_async(paper)

    try:
        stored = repo.store_review_state(state)
        print("✅ Stored review")
        print(f"review_id: {stored.review_id}")

        bundle = repo.fetch_review_bundle(stored.review_id)
        print("✅ Replayed review bundle")
        print(f"messages: {len(bundle.get('agent_messages') or [])}")
        print(f"verdict_versions: {len(bundle.get('verdict_versions') or [])}")

        # Create a second version (forward-only note) and compare.
        note = "Human feedback (simulated): tighten language around evidence strength; add explicit limitations section."
        v2 = repo.apply_forward_change_note_as_new_version(review_id=stored.review_id, forward_change_note=note)
        print("✅ Appended verdict version")
        print(f"version: {v2['version']}")

        diff = repo.compare_verdict_versions(stored.review_id, 1, int(v2["version"]))
        print("✅ Compared verdict versions")
        print(f"a.version: {diff['a']['version']}")
        print(f"b.version: {diff['b']['version']}")

    except Exception as exc:
        print("UNVERIFIED: Failed to store/replay review.")
        print(f"Error: {type(exc).__name__}: {exc}")
        print("Common causes: schema.sql not applied, RLS preventing inserts, publishable key lacks write access.")
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
