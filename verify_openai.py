#!/usr/bin/env python3
"""Verify OpenAI API key loading + basic connectivity.

- Loads `.env` from project root by default.
- Never prints the API key.

Usage:
  uv run python verify_openai.py
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    env_path = Path(os.getenv("SCIJUDGE_ENV_PATH", ".env")).expanduser().resolve()
    if env_path.exists():
        load_dotenv(env_path, override=True)
        print(f"dotenv: loaded {env_path}")
    else:
        print(f"dotenv: not found at {env_path} (continuing)")

    key = os.getenv("OPENAI_API_KEY")
    print(f"OPENAI_API_KEY set: {bool(key)}")
    print(f"OPENAI_API_KEY length: {len(key) if key else 0}")

    if not key:
        print("UNVERIFIED: OPENAI_API_KEY is missing.")
        return 2

    # Minimal API call via LangChain to validate auth.
    try:
        from langchain_openai import ChatOpenAI

        model = os.getenv("SCIJUDGE_OPENAI_MODEL", "gpt-4o-mini")
        llm = ChatOpenAI(model=model, temperature=0, max_tokens=1, timeout=30)
        _ = llm.invoke("ping")
        print(f"✅ OpenAI call succeeded (model={model})")
        return 0
    except Exception as exc:
        print("UNVERIFIED: OpenAI call failed.")
        print(f"Error: {type(exc).__name__}: {exc}")
        print("Common causes: invalid key, wrong project/org scope, network/TLS issues.")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
