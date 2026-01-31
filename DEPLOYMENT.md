# Deployment & Integration Guide

## System Overview

The Scientific Paper Judgment System is **architecturally complete** with all 8 phases implemented and verified. This guide details how to integrate LLMs and deploy for production use.

---

## Current Status

### ✅ Completed Components

| Phase | Component                 | Status     | Verification                |
| ----- | ------------------------- | ---------- | --------------------------- |
| 0     | Constitutional Principles | ✅ Complete | SCIENTIFIC_PRINCIPLES.md    |
| 1     | MCP Server & Diagnostics  | ✅ Complete | test_mcp_server.py passes   |
| 2     | LangGraph Orchestration   | ✅ Complete | State machine functional    |
| 3     | 6 Agent Specifications    | ✅ Complete | Full specs with constraints |
| 4     | Author Research Tools     | ✅ Complete | COI analysis structured     |
| 5     | arXiv Ingestion           | ✅ Complete | PDF parsing implemented     |
| 6     | Judgment Protocol         | ✅ Complete | 6-step debate sequence      |
| 7     | Report Generation         | ✅ Complete | MD, tables, JSON artifacts  |
| 8     | System Verification       | ✅ Complete | End-to-end demo successful  |

### 🔧 Integration Required

1. **LLM Connection**: Agents need LLM backends (Claude, GPT-4, etc.)
2. **API Integration**: Author research tools need external APIs
3. **Production Storage**: Persistent audit trail storage
4. **Web Interface**: Optional UI for non-programmatic access

---

## LLM Integration

### Option 1: OpenAI GPT-4

```python
from langchain_openai import ChatOpenAI
from scientific_judgment_mcp.agents import MODERATOR_SPEC

# Initialize LLM for moderator
moderator_llm = ChatOpenAI(
    model="gpt-4",
    temperature=0.3,  # Lower temp for consistency
)

# Create agent with system prompt
from langgraph.prebuilt import create_react_agent

moderator_agent = create_react_agent(
    model=moderator_llm,
    tools=[],  # Add MCP tools here
    state_modifier=MODERATOR_SPEC.system_prompt,
)
```

### Option 2: Anthropic Claude

```python
from langchain_anthropic import ChatAnthropic

# Recommended for epistemic humility
claude_llm = ChatAnthropic(
    model="claude-3-5-sonnet-20241022",
    temperature=0.3,
)

# Use same pattern as above
```

### Environment Variables

Create `.env` file:

```bash
# LLM API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Optional: Author Research APIs
ORCID_API_KEY=...
CROSSREF_EMAIL=your@email.com
```

---

## Enhanced Author Research

### ORCID Integration

```python
import httpx

async def fetch_orcid_profile(orcid_id: str) -> dict:
    """Fetch author profile from ORCID."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://pub.orcid.org/v3.0/{orcid_id}/record",
            headers={"Accept": "application/json"},
        )
        return response.json()
```

### Google Scholar (via serpapi)

```python
from serpapi import GoogleScholarSearch

def search_author_publications(author_name: str) -> list[dict]:
    """Search Google Scholar for author publications."""
    params = {
        "engine": "google_scholar_author",
        "author": author_name,
        "api_key": os.getenv("SERPAPI_KEY"),
    }

    search = GoogleScholarSearch(params)
    return search.get_dict().get("articles", [])
```

### NIH RePORTER (for funding)

```python
async def search_nih_funding(investigator_name: str) -> list[dict]:
    """Search NIH RePORTER for funding information."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.reporter.nih.gov/v2/projects/search",
            json={
                "criteria": {
                    "pi_names": [{"any_name": investigator_name}]
                }
            },
        )
        return response.json().get("results", [])
```

---

## Real arXiv Testing

### Fetch and Review a Real Paper

```python
import asyncio
from pathlib import Path
from scientific_judgment_mcp.tools.arxiv import ingest_arxiv_paper
from scientific_judgment_mcp.orchestration import run_debate
from scientific_judgment_mcp.reports import generate_all_artifacts

async def review_paper(arxiv_id: str):
    """Review a real arXiv paper."""

    # Ingest paper
    print(f"Fetching arXiv paper: {arxiv_id}")
    paper = await ingest_arxiv_paper(arxiv_id)

    # Run debate (with LLM-connected agents)
    print("Running scientific review panel...")
    final_state = run_debate(paper)

    # Generate reports
    print("Generating reports...")
    artifacts = generate_all_artifacts(
        final_state,
        output_dir=Path(f"./reports/{arxiv_id}")
    )

    print(f"\nReview complete:")
    for name, path in artifacts.items():
        print(f"  {name}: {path}")

    return final_state, artifacts

# Example usage
asyncio.run(review_paper("2401.12345"))
```

### Known PDF Extraction Issues

1. **Multi-column layouts**: May interleave text incorrectly
2. **Equations**: Often garbled or missing
3. **Figures/tables**: Captions may be separated from content
4. **Headers/footers**: May be included in section text

**Mitigation**:
- Use higher-quality PDF parsers (e.g., `pdfplumber`, `fitz`)
- Implement LaTeX source fetching (arXiv provides `.tex` files)
- Add manual review flags for critical sections

---

## Production Deployment

### 1. Persistent Storage

```python
# Use PostgreSQL for audit trails
from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class PaperReview(Base):
    __tablename__ = "paper_reviews"

    id = Column(Integer, primary_key=True)
    arxiv_id = Column(String, unique=True, index=True)
    review_data = Column(JSON)  # Full DebateState
    created_at = Column(DateTime)

engine = create_engine("postgresql://user:pass@localhost/sciencereview")
Base.metadata.create_all(engine)
```

### 2. Web API (FastAPI)

```python
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel

app = FastAPI(title="Scientific Paper Judgment API")

class ReviewRequest(BaseModel):
    arxiv_id: str

@app.post("/review")
async def create_review(request: ReviewRequest, background_tasks: BackgroundTasks):
    """Start a paper review (async)."""

    # Queue review as background task
    background_tasks.add_task(review_paper, request.arxiv_id)

    return {
        "status": "queued",
        "arxiv_id": request.arxiv_id,
        "message": "Review started. Check /review/{arxiv_id} for status.",
    }

@app.get("/review/{arxiv_id}")
async def get_review(arxiv_id: str):
    """Get review status and results."""
    # Query database
    # Return report
    pass
```

### 3. Authentication & Access Control

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token."""
    token = credentials.credentials
    # Validate token
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return user_from_token(token)

@app.post("/review", dependencies=[Depends(verify_token)])
async def create_review(...):
    ...
```

### 4. Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/review")
@limiter.limit("10/hour")  # Max 10 reviews per hour
async def create_review(...):
    ...
```

---

## Monitoring & Audit

### Principle Violation Tracking

```python
from prometheus_client import Counter

principle_violations = Counter(
    "principle_violations_total",
    "Total principle violations detected",
    ["principle", "agent"]
)

# In debate code:
if violation_detected:
    principle_violations.labels(
        principle="anti_orthodoxy_bias",
        agent="methodologist"
    ).inc()
```

### Review Quality Metrics

```python
from datadog import statsd

# Track review completion times
statsd.histogram("review.duration", duration_seconds)

# Track verdict distributions
statsd.increment(f"verdict.methodology.{score}")
```

---

## Testing Strategy

### Unit Tests

```bash
pytest tests/test_agents.py          # Agent specification tests
pytest tests/test_orchestration.py   # State machine tests
pytest tests/test_tools.py           # MCP tool tests
pytest tests/test_principles.py      # Principle enforcement tests
```

### Integration Tests

```python
# tests/test_full_review.py

async def test_full_review_pipeline():
    """Test complete review from arXiv ID to report."""

    # Use a well-known paper as test fixture
    arxiv_id = "1706.03762"  # "Attention is All You Need"

    paper = await ingest_arxiv_paper(arxiv_id)
    assert paper.title is not None

    final_state = run_debate(paper)
    assert final_state["phase"] == DebatePhase.COMPLETE

    artifacts = generate_all_artifacts(final_state)
    assert artifacts["markdown_report"].exists()
```

### Principle Compliance Tests

```python
def test_anti_orthodoxy_bias():
    """Ensure non-mainstream papers aren't discriminated against."""

    # Create two identical papers, one with "mainstream" framing
    mainstream_paper = create_mock_paper(framing="mainstream")
    heterodox_paper = create_mock_paper(framing="heterodox")

    state1 = run_debate(mainstream_paper)
    state2 = run_debate(heterodox_paper)

    # Verify methodological scores are similar
    assert abs(
        state1["verdict"].methodological_soundness -
        state2["verdict"].methodological_soundness
    ) <= 1  # Allow 1-point variation
```

---

## Scaling Considerations

### Parallel Reviews

```python
import asyncio
from concurrent.futures import ProcessPoolExecutor

async def review_batch(arxiv_ids: list[str]):
    """Review multiple papers in parallel."""

    with ProcessPoolExecutor() as executor:
        loop = asyncio.get_event_loop()

        tasks = [
            loop.run_in_executor(executor, run_debate, await ingest_arxiv_paper(id))
            for id in arxiv_ids
        ]

        results = await asyncio.gather(*tasks)

    return results
```

### Caching

```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=1000)
def cached_arxiv_fetch(arxiv_id: str) -> bytes:
    """Cache PDF downloads."""
    # Returns cached PDF bytes
    pass
```

---

## Ethical & Legal Considerations

### Data Retention

- **Audit Trails**: Retain for scientific reproducibility
- **Personal Data**: Comply with GDPR/CCPA for author information
- **Anonymization**: Option to anonymize COI reports

### Terms of Service

Users must acknowledge:
1. This is a tool, not a replacement for human judgment
2. Multi-axis verdicts are informative, not prescriptive
3. Principle violations are flagged but require human interpretation
4. The system has limitations (stated in every report)

### Responsible Use Policy

**Prohibited Uses**:
- Automated rejection of papers
- Public "blacklisting" based on COI findings
- Using verdicts to override peer review without examination

**Encouraged Uses**:
- Internal triage and prioritization
- Identifying methodological concerns for deeper review
- Training reviewers on epistemic principles
- Surfacing overlooked non-mainstream work

---

## Maintenance & Updates

### Updating Principles

```bash
# Principles can only be changed via formal amendment
git diff SCIENTIFIC_PRINCIPLES.md

# Must document:
# 1. Failure mode that triggered amendment
# 2. Evidence principle enabled invalid reasoning
# 3. Proposed revision
# 4. Verification new version prevents failure
```

### Agent Spec Updates

```python
# agents/specifications.py

# Version agent specs
MODERATOR_SPEC_V1 = AgentSpec(...)
MODERATOR_SPEC_V2 = AgentSpec(...)  # Document changes

# Allow version selection
def get_agent_spec(agent_role: str, version: int = 2):
    ...
```

### Dependency Updates

```bash
# Check for security updates
uv pip list --outdated

# Update with care (test thoroughly)
uv pip install --upgrade langgraph

# Pin critical versions
uv add "langgraph==1.0.7"
```

---

## Support & Community

### Reporting Issues

When reporting issues, include:
1. Full `DebateState` JSON
2. arXiv ID of paper reviewed
3. Specific principle or agent behavior in question
4. Expected vs. actual verdict

### Contributing

Contributions must:
1. Not violate constitutional principles
2. Include tests for new functionality
3. Update documentation
4. Pass principle compliance tests

---

## License & Citation

[To be determined]

If using this system in research, cite:

```
@software{scientific_judgment_system_2026,
  title={Scientific Paper Judgment System: A Fair, Structured, and Adversarial AI Framework},
  author={[Authors]},
  year={2026},
  url={https://github.com/...},
  note={Constitutional principles defined in SCIENTIFIC_PRINCIPLES.md}
}
```

---

## Conclusion

This system is a **scientific instrument** built with:
- ✅ Epistemic humility
- ✅ Transparent architecture
- ✅ Explicit principles
- ✅ Complete audit trails
- ✅ No shortcuts or compressed steps

It is ready for LLM integration and production deployment.

**Treat it as you would any precision instrument: with care, calibration, and respect for its limitations.**

---

**Version**: 1.0.0
**Status**: Architecturally Complete
**Last Updated**: 2026-01-30
