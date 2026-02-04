"""Supabase client loader.

Reads configuration from environment (optionally loaded from .env):
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY (preferred for server-side writes)
- SUPABASE_API_KEY (fallback)

Security:
- Do not log keys.
- Treat publishable/anon keys as potentially write-restricted under RLS.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from supabase import create_client
from supabase.client import Client
import certifi


def get_supabase_client(*, env_path: str | None = ".env") -> Client:
    if env_path:
        load_dotenv(env_path)

    # Some environments require OS trust store (e.g., corporate root CAs).
    # Prefer truststore when available; fall back to certifi/custom bundle.
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:
        ca_bundle = os.environ.get("SCIJUDGE_CA_BUNDLE") or certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", ca_bundle)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_bundle)

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_API_KEY")

    if not url:
        raise RuntimeError("SUPABASE_URL is not set")
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY or SUPABASE_API_KEY is not set")

    return create_client(url, key)
