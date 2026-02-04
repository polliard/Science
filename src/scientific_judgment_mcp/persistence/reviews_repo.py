"""Append-only review persistence.

Implements Phase 9.4 auditability requirements using Supabase.

Design goals:
- Judgments are append-only (no overwriting)
- Verdicts are versioned
- Human feedback is immutable and linked
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from supabase.client import Client

from scientific_judgment_mcp.orchestration import DebateState, PaperContext


@dataclass(frozen=True)
class StoredReview:
    review_id: str
    paper_id: str
    created_at: str
    version: int


class ReviewsRepository:
    def __init__(self, client: Client) -> None:
        self.client = client

    def ensure_paper(self, paper: PaperContext) -> str:
        """Insert paper if missing; returns paper_id.

        This does not modify existing judgments; paper metadata may be upserted.
        """

        # First try to find existing.
        existing = (
            self.client.table("papers")
            .select("id")
            .eq("arxiv_id", paper.arxiv_id)
            .execute()
        ).data

        if existing:
            return existing[0]["id"]

        paper_row = {
            "arxiv_id": paper.arxiv_id,
            "title": paper.title,
            "authors": paper.authors,
            "abstract": paper.abstract,
        }

        inserted = self.client.table("papers").insert(paper_row).execute().data
        if not inserted:
            raise RuntimeError("Failed to insert paper")
        return inserted[0]["id"]

    def create_review(self, *, paper_id: str, agent_model_configs: dict[str, Any]) -> str:
        review_id = str(uuid4())
        row = {
            "id": review_id,
            "paper_id": paper_id,
            "agent_model_configs": agent_model_configs,
        }
        self.client.table("reviews").insert(row).execute()
        return review_id

    def append_agent_messages(self, *, review_id: str, messages: list[dict[str, Any]]) -> None:
        rows = []
        for m in messages:
            rows.append(
                {
                    "id": str(uuid4()),
                    "review_id": review_id,
                    "agent": m.get("agent"),
                    "phase": m.get("phase"),
                    "timestamp": (m.get("timestamp") or datetime.now().isoformat()),
                    "content": m.get("content"),
                    "model_provider": m.get("model_provider"),
                    "model_name": m.get("model_name"),
                    "temperature": m.get("temperature"),
                    "max_tokens": m.get("max_tokens"),
                    "references_json": m.get("references") or [],
                    "flags_violation": bool(m.get("flags_violation") or False),
                }
            )

        if rows:
            self.client.table("agent_messages").insert(rows).execute()

    def create_verdict_version(self, *, review_id: str, version: int, verdict: dict[str, Any], synthesis: str) -> str:
        verdict_id = str(uuid4())
        row = {
            "id": verdict_id,
            "review_id": review_id,
            "version": version,
            "verdict": verdict,
            "synthesis": synthesis,
        }
        self.client.table("verdict_versions").insert(row).execute()
        return verdict_id

    def get_latest_verdict_version(self, review_id: str) -> dict[str, Any] | None:
        rows = (
            self.client.table("verdict_versions")
            .select("*")
            .eq("review_id", review_id)
            .order("version", desc=True)
            .limit(1)
            .execute()
        ).data
        return rows[0] if rows else None

    def append_verdict_version(self, *, review_id: str, verdict: dict[str, Any], synthesis: str) -> dict[str, Any]:
        latest = self.get_latest_verdict_version(review_id)
        next_version = int(latest["version"]) + 1 if latest else 1
        verdict_id = self.create_verdict_version(
            review_id=review_id,
            version=next_version,
            verdict=verdict,
            synthesis=synthesis,
        )
        return {"verdict_id": verdict_id, "version": next_version}

    def apply_forward_change_note_as_new_version(self, *, review_id: str, forward_change_note: str) -> dict[str, Any]:
        """Create a new verdict version that appends a forward-only note.

        This intentionally does not attempt to "fix" the past verdict; it records a new version.
        """

        latest = self.get_latest_verdict_version(review_id)
        if not latest:
            raise RuntimeError("No existing verdict version found for review")

        new_synthesis = (latest.get("synthesis") or "").rstrip() + "\n\n---\nForward-only change note:\n" + forward_change_note
        return self.append_verdict_version(
            review_id=review_id,
            verdict=latest.get("verdict") or {},
            synthesis=new_synthesis,
        )

    def store_review_state(self, state: DebateState) -> StoredReview:
        paper_id = self.ensure_paper(state["paper"])
        review_id = self.create_review(paper_id=paper_id, agent_model_configs=state.get("agent_model_configs", {}))

        # append-only messages
        self.append_agent_messages(
            review_id=review_id,
            messages=[m.model_dump(mode="json") for m in state["messages"]],
        )

        version = 1
        verdict = state.get("verdict")
        verdict_dict = verdict.model_dump(mode="json") if verdict else {}
        self.create_verdict_version(
            review_id=review_id,
            version=version,
            verdict=verdict_dict,
            synthesis=state.get("synthesis", ""),
        )

        return StoredReview(review_id=review_id, paper_id=paper_id, created_at=datetime.now().isoformat(), version=version)

    def add_human_feedback(
        self,
        *,
        review_id: str,
        critique_text: str,
        classification: dict[str, Any],
        forward_change_note: str,
    ) -> str:
        feedback_id = str(uuid4())
        row = {
            "id": feedback_id,
            "review_id": review_id,
            "critique_text": critique_text,
            "classification": classification,
            "forward_change_note": forward_change_note,
        }
        self.client.table("human_feedback").insert(row).execute()
        return feedback_id

    def fetch_review_bundle(self, review_id: str) -> dict[str, Any]:
        """Replay support: fetch review + messages + verdict versions + feedback."""

        review = self.client.table("reviews").select("*").eq("id", review_id).single().execute().data
        verdicts = self.client.table("verdict_versions").select("*").eq("review_id", review_id).order("version").execute().data
        messages = self.client.table("agent_messages").select("*").eq("review_id", review_id).order("timestamp").execute().data
        feedback = self.client.table("human_feedback").select("*").eq("review_id", review_id).order("created_at").execute().data

        return {
            "review": review,
            "verdict_versions": verdicts,
            "agent_messages": messages,
            "human_feedback": feedback,
        }

    def list_recent_reviews(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = (
            self.client.table("reviews")
            .select("id, paper_id, created_at")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        ).data
        return rows or []

    def list_papers_with_reviews(self, *, limit: int = 50, reviews_scan_limit: int = 500) -> list[dict[str, Any]]:
        """Return papers that have at least one review.

        Supabase/PostgREST grouping is intentionally avoided here for simplicity.
        We scan recent reviews, then fetch the corresponding papers.
        """

        recent_reviews = (
            self.client.table("reviews")
            .select("id, paper_id, created_at")
            .order("created_at", desc=True)
            .limit(reviews_scan_limit)
            .execute()
        ).data or []

        paper_ids: list[str] = []
        for r in recent_reviews:
            pid = r.get("paper_id")
            if pid and pid not in paper_ids:
                paper_ids.append(pid)
            if len(paper_ids) >= limit:
                break

        if not paper_ids:
            return []

        papers = (
            self.client.table("papers")
            .select("id, arxiv_id, title, created_at")
            .in_("id", paper_ids)
            .execute()
        ).data or []

        counts: dict[str, int] = {}
        latest_review: dict[str, str] = {}
        latest_created_at: dict[str, str] = {}
        for r in recent_reviews:
            pid = r.get("paper_id")
            if not pid:
                continue
            counts[pid] = counts.get(pid, 0) + 1
            # recent_reviews is ordered desc, so first seen is latest
            if pid not in latest_review:
                latest_review[pid] = r.get("id")
                latest_created_at[pid] = r.get("created_at")

        paper_by_id = {p["id"]: p for p in papers if p.get("id")}
        result = []
        for pid in paper_ids:
            p = paper_by_id.get(pid)
            if not p:
                continue
            result.append(
                {
                    "paper_id": pid,
                    "arxiv_id": p.get("arxiv_id"),
                    "title": p.get("title"),
                    "paper_created_at": p.get("created_at"),
                    "review_count": counts.get(pid, 0),
                    "latest_review_id": latest_review.get(pid),
                    "latest_review_created_at": latest_created_at.get(pid),
                }
            )

        # Keep same order as paper_ids derived from recent reviews
        return result

    def list_reviews_for_paper(self, *, paper_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = (
            self.client.table("reviews")
            .select("id, paper_id, created_at")
            .eq("paper_id", paper_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        ).data
        return rows or []

    def get_paper(self, paper_id: str) -> dict[str, Any]:
        return self.client.table("papers").select("*").eq("id", paper_id).single().execute().data

    def compare_verdict_versions(self, review_id: str, v1: int, v2: int) -> dict[str, Any]:
        a = self.client.table("verdict_versions").select("*").eq("review_id", review_id).eq("version", v1).single().execute().data
        b = self.client.table("verdict_versions").select("*").eq("review_id", review_id).eq("version", v2).single().execute().data
        return {"a": a, "b": b}
