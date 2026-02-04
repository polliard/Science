from __future__ import annotations

import os
from dotenv import load_dotenv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast
import re
import asyncio
from uuid import uuid4

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from scientific_judgment_mcp.feedback import (
    classify_human_critique,
    compare_feedback_to_review,
    propose_forward_change,
)
from scientific_judgment_mcp.orchestration.debate_protocol import (
    run_debate_async,
    register_progress_callback,
    unregister_progress_callback,
)
from scientific_judgment_mcp.reports import generate_all_artifacts
from scientific_judgment_mcp.publishability import evaluate_publishability
from scientific_judgment_mcp.persistence.reviews_repo import ReviewsRepository
from scientific_judgment_mcp.persistence.jobs_repo import JobsRepository
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


def _maybe_inject_truststore() -> bool:
    """Attempt to use OS trust store for TLS.

    Some environments have custom root CAs in the OS keychain (e.g., corporate MITM).
    Python's default CA bundle (certifi/OpenSSL) may not include them.
    """

    try:
        import truststore

        truststore.inject_into_ssl()
        return True
    except Exception:
        return False


TRUSTSTORE_INJECTED = _maybe_inject_truststore()

REPORTS_DIR = Path(os.getenv("SCIJUDGE_REPORTS_DIR", "reports")).resolve()


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="Scientific Judgment (Phase 9)")


@dataclass
class ReviewArtifacts:
    report_md: Path
    claims_json: Path | None
    summary_json: Path | None


@dataclass
class ReviewJob:
    job_id: str
    created_at: str
    status: str  # queued|running|complete|error
    step: str
    arxiv_id_or_url: str
    normalized_arxiv_id: str | None
    allow_insecure_tls: bool
    persist_to_supabase: bool
    num_reviews: int
    current_run: int
    messages_count: int
    last_agent: str | None
    last_phase: str | None
    error: str | None
    artifacts: list[dict[str, Any]]
    persisted_reviews: list[dict[str, Any]]


_JOBS: dict[str, ReviewJob] = {}
_JOBS_LOCK = asyncio.Lock()

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


def _jobs_repo_status() -> tuple[JobsRepository | None, str | None]:
    try:
        client = get_supabase_client(env_path=None)
        return JobsRepository(client), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _maybe_get_jobs_repo() -> JobsRepository | None:
    repo, _err = _jobs_repo_status()
    return repo


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


@app.get("/health/llm")
async def health_llm() -> JSONResponse:
    """Smoke-test OpenAI connectivity.

    This endpoint performs a minimal request (max_tokens=1) and returns a simple status.
    It never returns secrets.
    """

    try:
        from langchain_openai import ChatOpenAI

        model = os.getenv("SCIJUDGE_OPENAI_MODEL", "gpt-4o-mini")
        llm = cast(Any, ChatOpenAI)(
            model=model,
            temperature=0,
            max_tokens=1,
            timeout=20,
        )
        _ = llm.invoke("ping")
        return JSONResponse(
            {
                "ok": True,
                "provider": "openai",
                "model": model,
                "tls": {"truststore_injected": TRUSTSTORE_INJECTED},
            }
        )
    except Exception as e:
        return JSONResponse(
            {
                "ok": False,
                "provider": "openai",
                "error": f"{type(e).__name__}: {e}",
                "tls": {"truststore_injected": TRUSTSTORE_INJECTED},
            },
            status_code=500,
        )


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "dotenv_loaded_from": DOTENV_LOADED_FROM,
        "reports_dir": str(REPORTS_DIR),
        "tls": {"truststore_injected": TRUSTSTORE_INJECTED},
    }


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
    paper_id = None
    review_row = (bundle.get("review") or {}) if isinstance(bundle, dict) else {}
    if isinstance(review_row, dict):
        paper_id = review_row.get("paper_id")
    verdicts = bundle.get("verdict_versions") or []
    versions = [v.get("version") for v in verdicts if v.get("version") is not None]
    versions_sorted = sorted({int(v) for v in versions})

    latest_verdict_row = verdicts[-1] if verdicts else None
    latest_verdict = (latest_verdict_row or {}).get("verdict") or None
    publishability = None
    if isinstance(latest_verdict, dict):
        publishability = latest_verdict.get("publishability")
    if publishability is None and latest_verdict is not None:
        publishability = evaluate_publishability(latest_verdict).to_dict()

    return templates.TemplateResponse(
        "review_detail.html",
        {
            "request": request,
            "review_id": review_id,
            "paper_id": str(paper_id) if paper_id else None,
            "bundle": bundle,
            "versions": versions_sorted,
            "publishability": publishability,
        },
    )


@app.get("/reviews/{review_id}/bundle.json")
async def download_review_bundle(review_id: str) -> JSONResponse:
    repo = _require_repo()
    bundle = repo.fetch_review_bundle(review_id)
    return JSONResponse(bundle)


def _extract_verdict_dimensions(verdict: dict[str, Any]) -> dict[str, int]:
    dims: dict[str, int] = {}
    for k in [
        "methodological_soundness",
        "evidence_strength",
        "novelty_value",
        "scientific_contribution",
        "risk_of_overreach",
    ]:
        v = verdict.get(k)
        if isinstance(v, int):
            dims[k] = v
    return dims


def _mean(values: list[int]) -> float:
    return (sum(values) / len(values)) if values else 0.0


@app.get("/papers/{paper_id}/compare", response_class=HTMLResponse)
async def compare_paper_reviews(request: Request, paper_id: str, include_reviewers: bool = True) -> Any:
    """Compare/contrast multiple independent reviews for the same paper.

    This is *not* a text diff; it focuses on consensus vs disagreement across runs.
    """

    repo = _require_repo()
    paper = repo.get_paper(paper_id)
    rows = repo.list_reviews_with_latest_verdicts_for_paper(paper_id=paper_id, limit=50)

    reviews: list[dict[str, Any]] = []
    decision_counts: dict[str, int] = {}

    for item in rows:
        review_row = (item or {}).get("review") or {}
        verdict_row = (item or {}).get("latest_verdict_version") or {}
        rid = review_row.get("id")
        if not rid:
            continue

        verdict = verdict_row.get("verdict")
        verdict_dict: dict[str, Any] = verdict if isinstance(verdict, dict) else {}
        dims = _extract_verdict_dimensions(verdict_dict)

        pub = None
        if isinstance(verdict_dict, dict):
            pub = verdict_dict.get("publishability")
        if pub is None:
            pub = evaluate_publishability(verdict_dict).to_dict()
        decision = str((pub or {}).get("decision") or "unknown")
        decision_counts[decision] = decision_counts.get(decision, 0) + 1

        reviewer_snips: list[dict[str, Any]] = []
        if include_reviewers:
            try:
                reviewer_snips = repo.list_agent_message_snippets(review_id=str(rid))
            except Exception:
                reviewer_snips = []

        synthesis = verdict_row.get("synthesis")
        synthesis_preview = ""
        if isinstance(synthesis, str):
            synthesis_preview = synthesis.strip().replace("\r\n", "\n").replace("\r", "\n")[:1200]

        reviews.append(
            {
                "review_id": str(rid),
                "created_at": review_row.get("created_at"),
                "verdict_version": verdict_row.get("version"),
                "dimensions": dims,
                "publishability": pub,
                "rationale": verdict_dict.get("rationale") if isinstance(verdict_dict.get("rationale"), str) else "",
                "synthesis_preview": synthesis_preview,
                "reviewers": reviewer_snips,
            }
        )

    # Compute consensus stats.
    dim_keys = [
        "methodological_soundness",
        "evidence_strength",
        "novelty_value",
        "scientific_contribution",
        "risk_of_overreach",
    ]
    dim_stats: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []

    for k in dim_keys:
        vals = [int(r["dimensions"][k]) for r in reviews if isinstance(r.get("dimensions"), dict) and k in r["dimensions"]]
        if not vals:
            continue
        stats = {
            "key": k,
            "mean": round(_mean(vals), 2),
            "min": min(vals),
            "max": max(vals),
            "range": max(vals) - min(vals),
            "values": vals,
        }
        dim_stats.append(stats)
        if stats["range"] >= 2:
            # Provide a compact view of which reviews are on which side.
            low = [r["review_id"] for r in reviews if r.get("dimensions", {}).get(k) == stats["min"]]
            high = [r["review_id"] for r in reviews if r.get("dimensions", {}).get(k) == stats["max"]]
            disagreements.append(
                {
                    "key": k,
                    "min": stats["min"],
                    "max": stats["max"],
                    "low_reviews": low,
                    "high_reviews": high,
                }
            )

    # Show newest first.
    reviews.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)

    return templates.TemplateResponse(
        "paper_compare.html",
        {
            "request": request,
            "paper": paper,
            "paper_id": paper_id,
            "reviews": reviews,
            "decision_counts": decision_counts,
            "dim_stats": dim_stats,
            "disagreements": disagreements,
            "include_reviewers": include_reviewers,
        },
    )


@app.post("/review", response_class=HTMLResponse)
async def run_review(
    request: Request,
    arxiv_id_or_url: str = Form(...),
    allow_insecure_tls: bool = Form(False),
    persist_to_supabase: bool = Form(False),
    num_reviews: int = Form(2),
) -> Any:
    # This route enqueues a background job so the browser connection doesn't time out.
    # Results are available under /jobs/{job_id}.
    job_id = str(uuid4())
    n = int(num_reviews) if int(num_reviews) > 0 else 1
    n = min(max(n, 1), 6)

    job = ReviewJob(
        job_id=job_id,
        created_at=datetime.now().isoformat(),
        status="submitted",
        step="submitted",
        arxiv_id_or_url=arxiv_id_or_url,
        normalized_arxiv_id=None,
        allow_insecure_tls=bool(allow_insecure_tls),
        persist_to_supabase=bool(persist_to_supabase),
        num_reviews=n,
        current_run=0,
        messages_count=0,
        last_agent=None,
        last_phase=None,
        error=None,
        artifacts=[],
        persisted_reviews=[],
    )

    async with _JOBS_LOCK:
        _JOBS[job_id] = job

    jobs_repo = _maybe_get_jobs_repo()
    if jobs_repo is not None:
        try:
            await asyncio.to_thread(
                jobs_repo.create_job,
                job={
                    "id": job_id,
                    "status": "submitted",
                    "step": "submitted",
                    "arxiv_id_or_url": arxiv_id_or_url,
                    "normalized_arxiv_id": None,
                    "allow_insecure_tls": bool(allow_insecure_tls),
                    "persist_to_supabase": bool(persist_to_supabase),
                    "num_reviews": n,
                    "current_run": 0,
                    "messages_count": 0,
                    "last_agent": None,
                    "last_phase": None,
                    "error": None,
                    "artifacts": [],
                    "persisted_reviews": [],
                },
            )
            await asyncio.to_thread(
                jobs_repo.append_event,
                job_id=job_id,
                event_type="state",
                payload={"status": "submitted", "step": "submitted"},
            )
        except Exception:
            # Best-effort: job UI still works in-memory.
            pass

    asyncio.create_task(_run_review_job(job_id))
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


def _job_to_dict(job: ReviewJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "created_at": job.created_at,
        "status": job.status,
        "step": job.step,
        "arxiv_id_or_url": job.arxiv_id_or_url,
        "normalized_arxiv_id": job.normalized_arxiv_id,
        "allow_insecure_tls": job.allow_insecure_tls,
        "persist_to_supabase": job.persist_to_supabase,
        "num_reviews": job.num_reviews,
        "current_run": job.current_run,
        "messages_count": job.messages_count,
        "last_agent": job.last_agent,
        "last_phase": job.last_phase,
        "error": job.error,
        "artifacts": job.artifacts,
        "persisted_reviews": job.persisted_reviews,
    }


def _normalize_job_row(row: dict[str, Any]) -> dict[str, Any]:
    # Supabase row uses `id`; UI expects `job_id`.
    out = dict(row)
    out["job_id"] = str(out.pop("id", out.get("job_id")))
    return out


async def _set_job(job_id: str, **kwargs: Any) -> None:
    async with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        for k, v in kwargs.items():
            setattr(job, k, v)

    jobs_repo = _maybe_get_jobs_repo()
    if jobs_repo is None:
        return

    patch: dict[str, Any] = {}
    for k, v in kwargs.items():
        if k in {
            "status",
            "step",
            "normalized_arxiv_id",
            "num_reviews",
            "current_run",
            "messages_count",
            "last_agent",
            "last_phase",
            "error",
        }:
            patch[k] = v
    if patch:
        try:
            await asyncio.to_thread(jobs_repo.update_job, job_id, patch=patch)
        except Exception:
            pass


async def _run_review_job(job_id: str) -> None:
    jobs_repo = _maybe_get_jobs_repo()
    await _set_job(job_id, status="adjudicating", step="starting")
    if jobs_repo is not None:
        try:
            await asyncio.to_thread(
                jobs_repo.append_event,
                job_id=job_id,
                event_type="state",
                payload={"status": "adjudicating", "step": "starting"},
            )
        except Exception:
            pass

    # arXiv ingestion uses env toggle for insecure TLS; scope it to this job.
    prior_insecure = os.environ.get("SCIJUDGE_INSECURE_SSL")
    thread_id = f"job:{job_id}"

    def _progress_cb(msg: Any, state: Any) -> None:
        # Best-effort progress update.
        try:
            asyncio.get_event_loop()
        except Exception:
            return
        try:
            # Update without blocking the worker.
            asyncio.create_task(
                _set_job(
                    job_id,
                    messages_count=len(state.get("messages") or []),
                    last_agent=str(getattr(msg, "agent", "")),
                    last_phase=str(getattr(msg, "phase", "")),
                    step="debating",
                )
            )
        except Exception:
            pass

        if jobs_repo is not None:
            try:
                payload = {
                    "agent": str(getattr(msg, "agent", "")),
                    "phase": str(getattr(msg, "phase", "")),
                    "timestamp": str(getattr(msg, "timestamp", "")),
                    "model_provider": str(getattr(msg, "model_provider", "") or ""),
                    "model_name": str(getattr(msg, "model_name", "") or ""),
                    "content_preview": str(getattr(msg, "content", "") or "")[:220],
                }
                asyncio.create_task(
                    asyncio.to_thread(
                        jobs_repo.append_event,
                        job_id=job_id,
                        event_type="agent_message",
                        payload=payload,
                    )
                )
            except Exception:
                pass

    register_progress_callback(thread_id, _progress_cb)

    try:
        allow_insecure_tls = False
        num_reviews = 1
        arxiv_id_or_url = ""
        async with _JOBS_LOCK:
            j = _JOBS.get(job_id)
            if j:
                allow_insecure_tls = j.allow_insecure_tls
                num_reviews = j.num_reviews
                arxiv_id_or_url = j.arxiv_id_or_url

        try:
            if allow_insecure_tls:
                os.environ["SCIJUDGE_INSECURE_SSL"] = "1"
            else:
                os.environ.pop("SCIJUDGE_INSECURE_SSL", None)

            await _set_job(job_id, step="ingesting")
            if jobs_repo is not None:
                try:
                    await asyncio.to_thread(
                        jobs_repo.append_event,
                        job_id=job_id,
                        event_type="step",
                        payload={"step": "ingesting"},
                    )
                except Exception:
                    pass
            normalized = _normalize_arxiv_id_or_url(arxiv_id_or_url)
            await _set_job(job_id, normalized_arxiv_id=normalized)
            paper = await ingest_arxiv_paper(normalized)
        finally:
            if prior_insecure is None:
                os.environ.pop("SCIJUDGE_INSECURE_SSL", None)
            else:
                os.environ["SCIJUDGE_INSECURE_SSL"] = prior_insecure

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        for i in range(1, num_reviews + 1):
            await _set_job(job_id, current_run=i, step=f"reviewing ({i}/{num_reviews})")
            if jobs_repo is not None:
                try:
                    await asyncio.to_thread(
                        jobs_repo.append_event,
                        job_id=job_id,
                        event_type="run_start",
                        payload={"run": i, "num_reviews": num_reviews},
                    )
                except Exception:
                    pass
            debate_state = await run_debate_async(paper, thread_id=thread_id)

            run_dir = REPORTS_DIR / paper.arxiv_id / datetime.now().strftime("%Y%m%d_%H%M%S")
            if num_reviews > 1:
                run_dir = run_dir.with_name(run_dir.name + f"_run{i}")
            artifacts_map = generate_all_artifacts(debate_state, run_dir)
            artifacts = _artifacts_from_map(artifacts_map)

            artifact_row = {
                "run": i,
                "report_md": artifacts.report_md.relative_to(REPORTS_DIR).as_posix(),
                "claims_json": artifacts.claims_json.relative_to(REPORTS_DIR).as_posix() if artifacts.claims_json else None,
                "summary_json": artifacts.summary_json.relative_to(REPORTS_DIR).as_posix() if artifacts.summary_json else None,
                "report_preview": artifacts.report_md.read_text(encoding="utf-8")[:20000],
            }

            async with _JOBS_LOCK:
                j = _JOBS.get(job_id)
                if j:
                    j.artifacts.append(artifact_row)

            if jobs_repo is not None:
                try:
                    await asyncio.to_thread(
                        jobs_repo.update_job,
                        job_id,
                        patch={"artifacts": (j.artifacts if j else [artifact_row])},
                    )
                except Exception:
                    pass

                try:
                    await asyncio.to_thread(
                        jobs_repo.append_event,
                        job_id=job_id,
                        event_type="artifacts",
                        payload={"run": i, "artifacts": artifact_row},
                    )
                except Exception:
                    pass

            # Optional persistence, one Supabase review row per run.
            if False:
                pass
            if True:
                async with _JOBS_LOCK:
                    j = _JOBS.get(job_id)
                    persist_to_supabase = bool(j.persist_to_supabase) if j else False
                if persist_to_supabase:
                    await _set_job(job_id, step=f"persisting ({i}/{num_reviews})")
                    repo = _maybe_get_repo()
                    if repo is None:
                        async with _JOBS_LOCK:
                            jj = _JOBS.get(job_id)
                            if jj:
                                jj.persisted_reviews.append({"run": i, "error": "Supabase not configured"})
                    else:
                        try:
                            stored = repo.store_review_state(debate_state)
                            async with _JOBS_LOCK:
                                jj = _JOBS.get(job_id)
                                if jj:
                                    jj.persisted_reviews.append(
                                        {
                                            "run": i,
                                            "review_id": stored.review_id,
                                            "paper_id": stored.paper_id,
                                            "created_at": stored.created_at,
                                            "version": stored.version,
                                        }
                                    )

                            if jobs_repo is not None:
                                try:
                                    await asyncio.to_thread(
                                        jobs_repo.update_job,
                                        job_id,
                                        patch={"persisted_reviews": jj.persisted_reviews if jj else []},
                                    )
                                except Exception:
                                    pass

                                try:
                                    await asyncio.to_thread(
                                        jobs_repo.append_event,
                                        job_id=job_id,
                                        event_type="persisted_review",
                                        payload={
                                            "run": i,
                                            "review_id": stored.review_id,
                                            "paper_id": stored.paper_id,
                                            "version": stored.version,
                                        },
                                    )
                                except Exception:
                                    pass
                        except Exception as e:
                            async with _JOBS_LOCK:
                                jj = _JOBS.get(job_id)
                                if jj:
                                    jj.persisted_reviews.append({"run": i, "error": str(e)})

                            if jobs_repo is not None:
                                try:
                                    await asyncio.to_thread(
                                        jobs_repo.update_job,
                                        job_id,
                                        patch={"persisted_reviews": jj.persisted_reviews if jj else []},
                                    )
                                except Exception:
                                    pass

                                try:
                                    await asyncio.to_thread(
                                        jobs_repo.append_event,
                                        job_id=job_id,
                                        event_type="persist_error",
                                        payload={"run": i, "error": str(e)},
                                    )
                                except Exception:
                                    pass

        await _set_job(job_id, status="adjudicated", step="complete")
        if jobs_repo is not None:
            try:
                await asyncio.to_thread(
                    jobs_repo.append_event,
                    job_id=job_id,
                    event_type="state",
                    payload={"status": "adjudicated", "step": "complete"},
                )
            except Exception:
                pass
    except Exception as e:
        await _set_job(job_id, status="error", step="error", error=f"{type(e).__name__}: {e}")
        if jobs_repo is not None:
            try:
                await asyncio.to_thread(
                    jobs_repo.append_event,
                    job_id=job_id,
                    event_type="state",
                    payload={"status": "error", "error": f"{type(e).__name__}: {e}"},
                )
            except Exception:
                pass
    finally:
        unregister_progress_callback(thread_id)


@app.get("/jobs/{job_id}.json")
async def job_status(job_id: str) -> JSONResponse:
    jobs_repo = _maybe_get_jobs_repo()
    if jobs_repo is not None:
        row = await asyncio.to_thread(jobs_repo.get_job, job_id)
        if row:
            return JSONResponse({"ok": True, "job": _normalize_job_row(row)})

    async with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return JSONResponse({"ok": False, "error": "Job not found"}, status_code=404)
        return JSONResponse({"ok": True, "job": _job_to_dict(job)})


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_page(request: Request, job_id: str) -> Any:
    jobs_repo = _maybe_get_jobs_repo()
    if jobs_repo is not None:
        row = await asyncio.to_thread(jobs_repo.get_job, job_id)
        if row:
            return templates.TemplateResponse(
                "job.html",
                {
                    "request": request,
                    "job": _normalize_job_row(row),
                },
            )

    async with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if not job:
        return HTMLResponse("Job not found", status_code=404)
    return templates.TemplateResponse(
        "job.html",
        {
            "request": request,
            "job": _job_to_dict(job),
        },
    )


@app.get("/jobs/{job_id}/events.json")
async def job_events(job_id: str, limit: int = 100) -> JSONResponse:
    jobs_repo = _maybe_get_jobs_repo()
    if jobs_repo is None:
        return JSONResponse({"ok": False, "error": "Supabase not configured"}, status_code=200)
    lim = min(max(int(limit), 1), 300)
    try:
        events = await asyncio.to_thread(jobs_repo.list_events, job_id, limit=lim)
        return JSONResponse({"ok": True, "events": events})
    except Exception as e:
        # Keep the frontend polling loop stable (it always expects JSON).
        hint = "If you just enabled job persistence, apply supabase/schema.sql in Supabase SQL editor and restart the web server."
        return JSONResponse(
            {"ok": False, "error": f"{type(e).__name__}: {e}", "hint": hint},
            status_code=200,
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
