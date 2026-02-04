"""Persistent job tracking for web review runs.

This repository supports a durable state flow for long-running adjudication:
- submitted -> adjudicating -> adjudicated (or error)

`review_jobs` is mutable for "current status".
`review_job_events` is append-only for auditability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from typing import cast

from supabase.client import Client


@dataclass(frozen=True)
class JobState:
    job_id: str
    status: str
    step: str
    updated_at: str


class JobsRepository:
    def __init__(self, client: Client) -> None:
        self.client = client

    def create_job(self, *, job: dict[str, Any]) -> None:
        """Insert a new job row."""
        self.client.table("review_jobs").insert(job).execute()

    def update_job(self, job_id: str, *, patch: dict[str, Any]) -> None:
        """Patch an existing job row."""
        patch = dict(patch)
        patch.setdefault("updated_at", datetime.now().isoformat())
        self.client.table("review_jobs").update(patch).eq("id", job_id).execute()

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        try:
            data = self.client.table("review_jobs").select("*").eq("id", job_id).single().execute().data
            if isinstance(data, dict):
                return cast(dict[str, Any], data)
            return None
        except Exception:
            return None

    def append_event(self, *, job_id: str, event_type: str, payload: dict[str, Any]) -> None:
        row = {
            "id": None,  # allow db default
            "job_id": job_id,
            "event_type": event_type,
            "payload": payload,
        }
        # Explicitly drop id so postgres default can apply.
        row.pop("id", None)
        self.client.table("review_job_events").insert(row).execute()

    def list_events(self, job_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        rows = (
            self.client.table("review_job_events")
            .select("*")
            .eq("job_id", job_id)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        ).data
        if not rows:
            return []
        if isinstance(rows, list):
            return [cast(dict[str, Any], r) for r in rows if isinstance(r, dict)]
        return []
