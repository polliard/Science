"""Persistence layer (Phase 9.4).

Uses Supabase (Postgres via API) for an append-only, auditable review trail.
"""

from .supabase_client import get_supabase_client
from .reviews_repo import ReviewsRepository

__all__ = [
    "get_supabase_client",
    "ReviewsRepository",
]
