from __future__ import annotations

import os
from dotenv import load_dotenv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import re

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from scientific_judgment_mcp.feedback import (
    classify_human_critique,
    compare_feedback_to_review,
    propose_forward_change,
)
from scientific_judgment_mcp.orchestration.debate_protocol import run_debate_async
from scientific_judgment_mcp.reports import generate_all_artifacts
from scientific_judgment_mcp.persistence.reviews_repo import ReviewsRepository
from scientific_judgment_mcp.persistence.supabase_client import get_supabase_client
from scientific_judgment_mcp.tools.arxiv import ingest_arxiv_paper


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parents[3]
TEMPLATES_DIR = BASE_DIR / "templates"


def _load_project_dotenv() -> str | None:
    """Load env vars for the web backend.

    - Respects SCIJUDGE_ENV_PATH if set
    - Falls back to <project_root>/.env then <cwd>/.env
    """

    candidates: list[Path] = []
    explicit = os.getenv("SCIJUDGE_ENV_PATH")
    if explicit and explicit.strip():
        candidates.append(Path(explicit).expanduser())
    candidates.append(PROJECT_ROOT / ".env")
    candidates.append(Path.cwd() / ".env")

    for p in candidates:
        try:
            if p.exists():
                load_dotenv(p, override=True)
                return str(p.resolve())
        except Exception:
            # If dotenv load fails for some reason, continue to next candidate.
            continue
    return None


DOTENV_LOADED_FROM = _load_project_dotenv()

REPORTS_DIR = Path(os.getenv("SCIJUDGE_REPORTS_DIR", "reports")).resolve()


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="Scientific Judgment (Phase 9)")


@dataclass
class ReviewArtifacts:
    report_md: Path
    claims_json: Path | None
    summary_json: Path | None

_ARXIV_ID_RE = re.compile(r"(?:(?:arxiv\.)?org/(?:abs|pdf)/)?(?P<id>\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?", re.IGNORECASE)


def _normalize_arxiv_id_or_url(value: str) -> str:
    v = value.strip()
    if v.lower().startswith("arxiv:"):
        return v.split(":", 1)[1].strip()
    m = _ARXIV_ID_RE.search(v)
    return (m.group("id") if m else v).strip()


def _artifacts_from_map(artifacts: dict[str, Path]) -> ReviewArtifacts:
    return ReviewArtifacts(
        report_md=artifacts["markdown_report"],
        claims_json=artifacts.get("claim_table"),
        summary_json=artifacts.get("json_summary"),
    )


def _maybe_get_repo() -> ReviewsRepository | None:
    repo, _err = _repo_status()
    return repo


def _repo_status() -> tuple[ReviewsRepository | None, str | None]:
    try:
        # get_supabase_client can load .env too, but we pre-load here so other config
        # (including host/port/reports dir) is also pulled from .env.
        client = get_supabase_client(env_path=None)
        return ReviewsRepository(client), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _require_repo() -> ReviewsRepository:
    repo, err = _repo_status()
    if repo is None:
        hint = "Supabase is not configured (or client init failed). Ensure .env is set and schema.sql is applied."
        if DOTENV_LOADED_FROM:
            hint += f" (dotenv loaded from: {DOTENV_LOADED_FROM})"
        if err:
            hint += f" (error: {err})"
        raise RuntimeError(hint)
    return repo


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> Any:
    _repo, repo_err = _repo_status()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "reports_dir": str(REPORTS_DIR),
            "supabase_configured": _repo is not None,
            "supabase_error": repo_err,
            "dotenv_loaded_from": DOTENV_LOADED_FROM,
        },
    )


@app.get("/reviews", response_class=HTMLResponse)
async def list_reviews(request: Request) -> Any:
    repo = _require_repo()
    reviews = repo.list_recent_reviews(limit=50)
    return templates.TemplateResponse(
        "reviews.html",
        {
            "request": request,
            "reviews": reviews,
        },
    )


@app.get("/papers", response_class=HTMLResponse)
async def list_papers(request: Request) -> Any:
    repo = _require_repo()
    papers = repo.list_papers_with_reviews(limit=50)
    return templates.TemplateResponse(
        "papers.html",
        {
            "request": request,
            "papers": papers,
        },
    )


@app.get("/papers/{paper_id}", response_class=HTMLResponse)
async def paper_detail(request: Request, paper_id: str) -> Any:
    repo = _require_repo()
    paper = repo.get_paper(paper_id)
    reviews = repo.list_reviews_for_paper(paper_id=paper_id, limit=50)
    return templates.TemplateResponse(
        "paper_detail.html",
        {
            "request": request,
            "paper": paper,
            "reviews": reviews,
        },
    )


@app.get("/reviews/{review_id}", response_class=HTMLResponse)
async def review_detail(request: Request, review_id: str) -> Any:
    repo = _require_repo()
    bundle = repo.fetch_review_bundle(review_id)
    verdicts = bundle.get("verdict_versions") or []
    versions = [v.get("version") for v in verdicts if v.get("version") is not None]
    versions_sorted = sorted({int(v) for v in versions})

    return templates.TemplateResponse(
        "review_detail.html",
        {
            "request": request,
            "review_id": review_id,
            "bundle": bundle,
            "versions": versions_sorted,
        },
    )


@app.get("/reviews/{review_id}/bundle.json")
async def download_review_bundle(review_id: str) -> JSONResponse:
    repo = _require_repo()
    bundle = repo.fetch_review_bundle(review_id)
    return JSONResponse(bundle)


@app.get("/reviews/{review_id}/compare", response_class=HTMLResponse)
async def compare_versions(request: Request, review_id: str, v1: int = 1, v2: int = 2) -> Any:
    import difflib

    repo = _require_repo()
    diff = repo.compare_verdict_versions(review_id, v1, v2)
    a = diff.get("a") or {}
    b = diff.get("b") or {}
    a_text = (a.get("synthesis") or "").splitlines(keepends=True)
    b_text = (b.get("synthesis") or "").splitlines(keepends=True)
    udiff = "".join(
        difflib.unified_diff(a_text, b_text, fromfile=f"v{v1}", tofile=f"v{v2}")
    )

    return templates.TemplateResponse(
        "compare.html",
        {
            "request": request,
            "review_id": review_id,
            "v1": v1,
            "v2": v2,
            "diff": udiff,
        },
    )


@app.post("/review", response_class=HTMLResponse)
async def run_review(
    request: Request,
    arxiv_id_or_url: str = Form(...),
    allow_insecure_tls: bool = Form(False),
    persist_to_supabase: bool = Form(False),
) -> Any:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # arXiv ingestion currently uses an environment variable toggle for insecure TLS.
    # We scope it to this request.
    prior_insecure = os.environ.get("SCIJUDGE_INSECURE_SSL")
    try:
        if allow_insecure_tls:
            os.environ["SCIJUDGE_INSECURE_SSL"] = "1"
        else:
            os.environ.pop("SCIJUDGE_INSECURE_SSL", None)

        paper = await ingest_arxiv_paper(_normalize_arxiv_id_or_url(arxiv_id_or_url))
    finally:
        if prior_insecure is None:
            os.environ.pop("SCIJUDGE_INSECURE_SSL", None)
        else:
            os.environ["SCIJUDGE_INSECURE_SSL"] = prior_insecure

    debate_state = await run_debate_async(paper)

    run_dir = REPORTS_DIR / paper.arxiv_id / datetime.now().strftime("%Y%m%d_%H%M%S")
    artifacts_map = generate_all_artifacts(debate_state, run_dir)
    artifacts = _artifacts_from_map(artifacts_map)

    persisted: dict[str, Any] | None = None
    persist_error: str | None = None

    if persist_to_supabase:
        repo = _maybe_get_repo()
        if repo is None:
            persist_error = "Supabase is not configured (or client init failed)."
        else:
            try:
                stored = repo.store_review_state(debate_state)
                persisted = {
                    "review_id": stored.review_id,
                    "paper_id": stored.paper_id,
                    "created_at": stored.created_at,
                    "version": stored.version,
                }
            except Exception as e:
                persist_error = str(e)

    return templates.TemplateResponse(
        "review.html",
        {
            "request": request,
            "arxiv_id_or_url": arxiv_id_or_url,
            "allow_insecure_tls": allow_insecure_tls,
            "persist_to_supabase": persist_to_supabase,
            "persisted": persisted,
            "persist_error": persist_error,
            "persisted_review_id": (persisted or {}).get("review_id"),
            "report_md": artifacts.report_md.relative_to(REPORTS_DIR).as_posix(),
            "claims_json": artifacts.claims_json.relative_to(REPORTS_DIR).as_posix() if artifacts.claims_json else None,
            "summary_json": artifacts.summary_json.relative_to(REPORTS_DIR).as_posix() if artifacts.summary_json else None,
            "report_preview": artifacts.report_md.read_text(encoding="utf-8")[:20000],
        },
    )


@app.get("/download/{filename:path}")
async def download(filename: str) -> FileResponse:
    path = (REPORTS_DIR / filename).resolve()
    if not str(path).startswith(str(REPORTS_DIR)):
        raise ValueError("Invalid path")
    return FileResponse(path)


@app.get("/feedback", response_class=HTMLResponse)
async def feedback_form(request: Request) -> Any:
    return templates.TemplateResponse(
        "feedback.html",
        {
            "request": request,
            "supabase_configured": _maybe_get_repo() is not None,
        },
    )


@app.post("/feedback", response_class=HTMLResponse)
async def submit_feedback(
    request: Request,
    review_id: str = Form(...),
    critique_text: str = Form(...),
) -> Any:
    classification = classify_human_critique(critique_text)

    stored: dict[str, Any] | None = None
    store_error: str | None = None
    change_note: str | None = None
    comparison: dict[str, Any] | None = None
    verdict_update: dict[str, Any] | None = None

    repo = _maybe_get_repo()
    if repo is None:
        store_error = "Supabase is not configured (or client init failed)."
    else:
        try:
            bundle = repo.fetch_review_bundle(review_id)
            comparison = compare_feedback_to_review(critique=classification, review_state=bundle)
            change_note = propose_forward_change(comparison=comparison)

            feedback_id = repo.add_human_feedback(
                review_id=review_id,
                critique_text=critique_text,
                classification=classification,
                forward_change_note=change_note,
            )
            verdict_update = repo.apply_forward_change_note_as_new_version(
                review_id=review_id,
                forward_change_note=change_note,
            )
            stored = {"feedback_id": feedback_id, "verdict_update": verdict_update}
        except Exception as e:
            store_error = str(e)

    return templates.TemplateResponse(
        "feedback.html",
        {
            "request": request,
            "supabase_configured": repo is not None,
            "submitted": True,
            "review_id": review_id,
            "classification": classification,
            "comparison": comparison,
            "change_note": change_note,
            "stored": stored,
            "verdict_update": verdict_update,
            "store_error": store_error,
        },
    )
