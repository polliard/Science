# Scientific Paper Judgment System

**A fair, structured, and adversarial AI system for evaluating scientific papers—including non-mainstream and paradigm-challenging work.**

## Core Principles

This system judges **scientific rigor**, not **conformity to consensus**.

See [SCIENTIFIC_PRINCIPLES.md](SCIENTIFIC_PRINCIPLES.md) for the complete constitutional foundation.

Key tenets:
1. **Methodological Neutrality** — Non-mainstream hypotheses receive equal evaluation
2. **Separation of Concerns** — Methodology ≠ Conclusions ≠ Implications
3. **Anti-Orthodoxy Bias Control** — "Contradicts consensus" triggers scrutiny, not rejection
4. **COI Awareness** — Surface conflicts of interest without guilt-by-association
5. **Progress-of-Science Test** — Value scientific contributions even when wrong

---

## Architecture Overview

### Technology Stack

**MCP Server** (Phase 1)
- **Runtime**: Python 3.14+ with `uv` package manager
- **Protocol**: Model Context Protocol (stdio transport)
- **Purpose**: Tool exposure for paper analysis, author research, and COI detection

**Orchestration** (Phase 2-3)
- Multi-agent deliberation framework (LangGraph/AutoGen/CrewAI)
- State machine for structured debate phases
- Audit trail for all agent reasoning

**Agents** (Phase 3)
1. **Moderator/Chair** — Enforces fairness, prevents pile-ons
2. **Methodologist** — Evaluates experimental design and statistics
3. **Evidence Auditor** — Verifies data sufficiency and logical support
4. **Paradigm Challenger** — Defends the right of non-mainstream ideas
5. **Skeptic** — Attempts falsification and alternative explanations
6. **Incentives & COI Analyst** — Researches funding and conflicts

### Directory Structure

```
Science/
├── SCIENTIFIC_PRINCIPLES.md    # Constitutional foundation (Phase 0)
├── README.md                    # This file
├── pyproject.toml               # Python dependencies
├── src/
│   └── scientific_judgment_mcp/
│       ├── __init__.py
│       ├── server.py            # MCP server (Phase 1)
│       ├── tools/               # MCP tool implementations
│       │   ├── arxiv.py         # arXiv ingestion (Phase 5)
│       │   ├── author_research.py  # Author background (Phase 4)
│       │   └── coi_analysis.py  # Conflict of interest detection
│       ├── agents/              # Agent definitions (Phase 3)
│       │   ├── moderator.py
│       │   ├── methodologist.py
│       │   ├── evidence_auditor.py
│       │   ├── paradigm_challenger.py
│       │   ├── skeptic.py
│       │   └── incentives_analyst.py
│       └── orchestration/       # Deliberation engine (Phase 2)
│           ├── debate_protocol.py
│           └── state_machine.py
├── reports/                     # Generated evaluations (Phase 7)
└── tests/                       # Verification (Phase 8)
```

---

## Phase Progress

### ✅ Phase 0: Scientific Principles
Constitutional foundation established in [SCIENTIFIC_PRINCIPLES.md](SCIENTIFIC_PRINCIPLES.md).

### 🚧 Phase 1: MCP Server Bootstrap
**Status**: In Progress

**Justification for `uv`**:
- Modern, fast dependency resolution
- Integrated virtual environment management
- Single-binary distribution
- Drop-in replacement for pip/poetry/pipenv
- Active development and strong community support

**Completed**:
- [x] Project initialization with `uv`
- [x] Core dependencies installed (mcp, httpx, arxiv, pydantic)
- [x] MCP server skeleton created
- [x] Diagnostic tools implemented:
  - `ping` — Health check
  - `env_info` — System information
  - `tool_inventory` — Available tools catalog

**Verification**:
```bash
cd /Users/itsfwcp/workspace/xdao.co/Science
uv run python -m scientific_judgment_mcp.server
# Then test with MCP inspector or direct JSON-RPC calls
```

### 📋 Phase 2: Orchestration Layer
**Status**: Not Started

### 📋 Phase 3: Scientific Review Panel
**Status**: Not Started

### 📋 Phase 4: Author Research Tools
**Status**: Not Started

### 📋 Phase 5: arXiv Ingestion
**Status**: Not Started

### 📋 Phase 6: Judgment Protocol
**Status**: Not Started

### 📋 Phase 7: Output Artifacts
**Status**: Not Started

### 📋 Phase 8: Verification
**Status**: Not Started

---

## Installation

```bash
# Clone or navigate to project
cd /Users/itsfwcp/workspace/xdao.co/Science

# Install dependencies (uv creates venv automatically)
uv sync

# Run MCP server
uv run python -m scientific_judgment_mcp.server
```

---

## Usage

### Web UI configuration (.env)

The FastAPI web UI (run via `python run_web.py`) reads these optional `.env` settings:

- `SCIJUDGE_MIN_FINAL_REVIEWS` (default: `5`): minimum independent reviews required for a **Final** publishability decision.
- `SCIJUDGE_MAX_ADDITIONAL_REVIEWS_REQUEST` (default: `5`): maximum *additional* reviews a user can request at once from the `/papers` UI.
- `SCIJUDGE_MAX_REVIEWS_PER_JOB` (default: `6`): hard cap on `num_reviews` per `/review` job.
- `SCIJUDGE_LOCK_REVIEW_AFTER_FINAL` (default: `true`): when `true`, disables re-review once a paper has at least `SCIJUDGE_MIN_FINAL_REVIEWS` persisted reviews (unless `force=true` is submitted).

Defaults for the home page form:

- `SCIJUDGE_DEFAULT_NUM_REVIEWS` (default: `2`): default value shown for “Independent review runs”.
- `SCIJUDGE_DEFAULT_ALLOW_INSECURE_TLS` (default: `false`): default checked state for “Allow insecure TLS”.
- `SCIJUDGE_DEFAULT_PERSIST_TO_SUPABASE` (default: `true`): default checked state for “Persist to Supabase” (only applies when Supabase is configured).

### Testing Diagnostic Tools

```bash
# Start server and send test requests
echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"ping","arguments":{}},"id":1}' \
  | uv run python -m scientific_judgment_mcp.server
```

### Evaluating a Paper (Future)

```python
from scientific_judgment_mcp import review_paper

report = review_paper(
    arxiv_id="2401.12345",
    panel_config="default",  # Uses all 6 agents
)

print(report.summary)
print(report.claim_table)
print(report.coi_appendix)
```

---

## Design Decisions

### Why MCP (Model Context Protocol)?

1. **Tool Composability** — Agents can invoke standardized tools
2. **Language Agnostic** — Python server, any client language
3. **Audit Trail** — All tool calls are loggable
4. **Stateless Tools** — Easier to reason about and test

### Why Multi-Agent Deliberation?

Single-agent evaluation risks:
- Overconfidence in initial interpretation
- Missing alternative explanations
- Implicit bias toward consensus views

Multi-agent debate:
- Forces explicit reasoning
- Surfaces contradictions
- Provides minority opinions
- Creates audit trail

### Why Multi-Axis Verdicts?

Binary "accept/reject" obscures nuance:
- Strong methods + weak evidence = reject?
- Weak methods + novel question = reject?
- Overreaching claims + useful data = reject?

Multi-axis scoring preserves information:
- **Methodology**: 4/5 (solid design)
- **Evidence**: 2/5 (underpowered)
- **Novelty**: 5/5 (new question)
- **Contribution**: 4/5 (useful even if wrong)
- **Overreach**: 4/5 (claims exceed data)

**Interpretation**: Worth reading, needs replication, claims should be softened.

---

## Failure Modes & Safeguards

| Failure Mode                                       | Detection                                 | Mitigation                                |
| -------------------------------------------------- | ----------------------------------------- | ----------------------------------------- |
| Consensus bias                                     | Paradigm Challenger agent silent          | Moderator enforces participation          |
| COI used to dismiss                                | Incentives Analyst overstepping           | Principles violation alert                |
| Methodological vs. ideological critique conflation | Moderator review                          | Transcript audit                          |
| Pile-on behavior                                   | Multiple agents using consensus arguments | Moderator intervention                    |
| Certainty overstatement                            | Lack of uncertainty caveats               | Final report requires limitations section |

---

## Verification Criteria

Each phase must demonstrate:

✅ **Functional**: Components respond as specified
✅ **Principled**: Outputs conform to SCIENTIFIC_PRINCIPLES.md
✅ **Auditable**: All reasoning and tool calls logged
✅ **Reproducible**: Same inputs yield same outputs (given deterministic LLM)

---

## Contributing

This system is a **scientific instrument**.

Modifications must:
1. Not violate constitutional principles
2. Improve epistemic accuracy
3. Enhance auditability
4. Be empirically verified

Convenience and preference are **not** grounds for changes.

---

## License

[To be determined]

---

## Contact

For questions about design decisions or principle interpretation, open an issue with:
- The specific principle in question
- The concrete case that triggers uncertainty
- Your proposed resolution

**Do not request features that would compromise epistemic principles.**

---

**Version**: 0.1.0 (Phase 1 in progress)
**Last Updated**: 2026-01-30
