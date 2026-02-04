from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

import uvicorn


def main() -> None:
    # Load env vars for local web backend.
    explicit = os.getenv("SCIJUDGE_ENV_PATH")
    if explicit and explicit.strip():
        load_dotenv(Path(explicit).expanduser(), override=True)
    else:
        # Project root is the directory containing this script.
        load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

    host = os.getenv("SCIJUDGE_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("SCIJUDGE_WEB_PORT", "8000"))

    uvicorn.run(
        "scientific_judgment_mcp.web.app:app",
        host=host,
        port=port,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
