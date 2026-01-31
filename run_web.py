from __future__ import annotations

import os

import uvicorn


def main() -> None:
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
