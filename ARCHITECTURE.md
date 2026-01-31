# System Architecture

## Overview

The Scientific Paper Judgment System is a multi-agent AI framework for fair, rigorous evaluation of scientific papers, including non-mainstream and paradigm-challenging work.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SCIENTIFIC_PRINCIPLES.md                         │
│                   (Constitutional Foundation)                        │
│                                                                      │
│  1. Methodological Neutrality                                       │
│  2. Separation of Concerns                                          │
│  3. Anti-Orthodoxy Bias Control                                     │
│  4. COI Awareness (not dismissal)                                   │
│  5. Progress-of-Science Test                                        │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│                         MCP SERVER (Phase 1)                         │
│                     (Model Context Protocol)                         │
│                                                                      │
│  ┌────────────────────┐  ┌────────────────────┐                    │
│  │  Diagnostic Tools  │  │   arXiv Ingestion  │                    │
│  │  - ping            │  │  - fetch_metadata  │                    │
│  │  - env_info        │  │  - download_pdf    │                    │
│  │  - tool_inventory  │  │  - extract_text    │                    │
│  └────────────────────┘  └────────────────────┘                    │
│                                                                      │
│  ┌────────────────────┐  ┌────────────────────┐                    │
│  │  Author Research   │  │   COI Analysis     │                    │
│  │  - research_author │  │  - find_funding    │                    │
│  │  - check_affil.    │  │  - analyze_coi     │                    │
│  └────────────────────┘  └────────────────────┘                    │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│                   ORCHESTRATION LAYER (Phase 2)                      │
│                          (LangGraph)                                 │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                 DEBATE STATE MACHINE                        │    │
│  │                                                              │    │
│  │  INIT → CLAIMS → METHODS → EVIDENCE → COI → PROGRESS →     │    │
│  │         ↓         ↓          ↓         ↓        ↓            │    │
│  │       DELIBERATION → VERDICT → SYNTHESIS → COMPLETE        │    │
│  │                                                              │    │
│  │  State: {paper, phase, messages, findings, verdict}         │    │
│  │  Checkpointing: MemorySaver (audit trail)                   │    │
│  └────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│              SCIENTIFIC REVIEW PANEL (Phase 3)                       │
│                    (6 Specialized Agents)                            │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐  │
│  │   MODERATOR      │  │  METHODOLOGIST   │  │ EVIDENCE AUDITOR│  │
│  │   (Chair)        │  │  (Design/Stats)  │  │ (Data/Citations)│  │
│  │                  │  │                  │  │                 │  │
│  │ - Enforce rules  │  │ - Exp. design    │  │ - Data adequacy │  │
│  │ - Prevent pile-on│  │ - Controls       │  │ - Citation check│  │
│  │ - Synthesize     │  │ - Statistics     │  │ - Logical gaps  │  │
│  └──────────────────┘  └──────────────────┘  └─────────────────┘  │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐  │
│  │   PARADIGM       │  │     SKEPTIC      │  │  INCENTIVES     │  │
│  │   CHALLENGER     │  │  (Falsification) │  │  ANALYST        │  │
│  │                  │  │                  │  │  (COI Research) │  │
│  │ - Defend rights  │  │ - Alternative    │  │ - Funding       │  │
│  │ - Flag consensus │  │   explanations   │  │ - Affiliations  │  │
│  │ - Historical ex. │  │ - Test robust.   │  │ - Career goals  │  │
│  └──────────────────┘  └──────────────────┘  └─────────────────┘  │
│                                                                      │
│  Each agent has:                                                    │
│  - System prompt from SCIENTIFIC_PRINCIPLES.md                      │
│  - Explicit constraints (what they CANNOT do)                       │
│  - Allowed/prohibited reasoning patterns                            │
│  - Tool permissions                                                 │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      JUDGMENT PROTOCOL (Phase 6)                     │
│                        (6-Step Sequence)                             │
│                                                                      │
│  Step 1: CLAIM ENUMERATION                                          │
│    - What does the paper actually claim?                            │
│    - Agents: Moderator, Evidence Auditor, Methodologist             │
│                                                                      │
│  Step 2: METHODOLOGICAL REVIEW                                      │
│    - Are methods appropriate for claims?                            │
│    - Agents: Moderator, Methodologist, Skeptic                      │
│    - CONSTRAINT: Cannot evaluate truth, only methods                │
│                                                                      │
│  Step 3: EVIDENCE SUFFICIENCY                                       │
│    - Does data support conclusions?                                 │
│    - Agents: Moderator, Evidence Auditor, Skeptic, Paradigm Chall. │
│    - CONSTRAINT: "Insufficient" ≠ "Contradicts consensus"           │
│                                                                      │
│  Step 4: COI REVIEW                                                 │
│    - Surface conflicts WITHOUT dismissal                            │
│    - Agents: Moderator, Incentives Analyst                          │
│    - CONSTRAINT: Surfacing ≠ Disqualification                       │
│                                                                      │
│  Step 5: PROGRESS-OF-SCIENCE EVALUATION                             │
│    - Does this advance inquiry, even if wrong?                      │
│    - Agents: Moderator, Paradigm Challenger, Evidence Auditor      │
│                                                                      │
│  Step 6: VERDICT ASSIGNMENT                                         │
│    - Multi-axis scoring (5 dimensions)                              │
│    - Agents: Moderator (synthesizes agent input)                    │
│    - OUTPUT: VerdictDimension object with rationale                 │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    OUTPUT GENERATION (Phase 7)                       │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  1. MARKDOWN REPORT (comprehensive)                         │    │
│  │     - Paper information                                     │    │
│  │     - Constitutional principles applied                     │    │
│  │     - Enumerated claims                                     │    │
│  │     - Multi-axis verdict table                              │    │
│  │     - Methodological review                                 │    │
│  │     - Evidence sufficiency                                  │    │
│  │     - COI analysis appendix                                 │    │
│  │     - Chair's synthesis                                     │    │
│  │     - Limitations & uncertainty                             │    │
│  │     - Audit trail                                           │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  2. CLAIM TABLE (structured)                                │    │
│  │     - Claim-by-claim breakdown                              │    │
│  │     - Methodology assessment per claim                      │    │
│  │     - Evidence assessment per claim                         │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  3. JSON SUMMARY (machine-readable)                         │    │
│  │     - Structured verdict data                               │    │
│  │     - Review metadata                                       │    │
│  │     - Findings by category                                  │    │
│  │     - Audit information                                     │    │
│  └────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Input → Processing → Output

```
arXiv ID (e.g., "2401.12345")
    ↓
[MCP Tool: fetch_arxiv_paper]
    ↓
PaperContext {
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    claims: list[str]
    methods: str
    results: str
    limitations: list[str]
}
    ↓
[Orchestration: run_debate(paper)]
    ↓
DebateState {
    paper: PaperContext
    phase: DebatePhase
    messages: list[AgentMessage]
    enumerated_claims: list[str]
    methodological_findings: dict
    evidence_findings: dict
    coi_findings: dict
    verdict: VerdictDimension
    synthesis: str
    principle_violations: list[str]
}
    ↓
[Reports: generate_all_artifacts(state)]
    ↓
{
    "markdown_report": Path("./reports/review_2401.12345.md"),
    "claim_table": Path("./reports/claims_2401.12345.md"),
    "json_summary": Path("./reports/summary_2401.12345.json"),
}
```

---

## Agent Interaction Pattern

### Phase: Evidence Review (Example)

```
Moderator:
  ↓ "Phase 3: Evidence Sufficiency Review.
  ↓  Evidence Auditor: Check data adequacy.
  ↓  Skeptic: Propose alternatives.
  ↓  Paradigm Challenger: Ensure fairness."
  ↓
  ├─→ Evidence Auditor
  │     ↓ [Invokes MCP tool: extract_results_section]
  │     ↓ [Analyzes data vs. claims]
  │     ↓ "Claim 1: Data shows X, but conclusion states Y.
  │     ↓  Gap: No evidence for causal mechanism."
  │     ↓
  ├─→ Skeptic
  │     ↓ "Alternative explanation: Confound Z could produce
  │     ↓  the same correlation. Not ruled out in paper."
  │     ↓
  ├─→ Paradigm Challenger
  │     ↓ "Critique is fair. However, ensure we're not
  │     ↓  requiring higher evidence bar because this
  │     ↓  contradicts current models."
  │     ↓
  ↓
Moderator:
  ↓ [Synthesizes findings]
  ↓ [Checks for principle violations]
  ↓ [Advances to next phase]
```

---

## State Machine Detail

### Debate Phases with Conditions

```
Phase: INITIALIZATION
  Condition: paper context loaded
  Participants: Moderator
  Transition: → CLAIM_ENUMERATION

Phase: CLAIM_ENUMERATION
  Condition: claims list populated
  Participants: Moderator, Evidence Auditor, Methodologist
  Transition: → METHODOLOGICAL_REVIEW

Phase: METHODOLOGICAL_REVIEW
  Condition: methodological findings recorded
  Participants: Moderator, Methodologist, Skeptic
  Transition: → EVIDENCE_REVIEW

Phase: EVIDENCE_REVIEW
  Condition: evidence findings recorded
  Participants: Moderator, Evidence Auditor, Skeptic, Paradigm Challenger
  Transition: → COI_REVIEW

Phase: COI_REVIEW
  Condition: COI findings recorded
  Participants: Moderator, Incentives Analyst
  Transition: → PROGRESS_EVALUATION

Phase: PROGRESS_EVALUATION
  Condition: progress assessment recorded
  Participants: Moderator, Paradigm Challenger, Evidence Auditor
  Transition: → DELIBERATION

Phase: DELIBERATION
  Condition: all agents had opportunity to contribute
  Participants: All 6 agents
  Transition: → VERDICT_ASSIGNMENT

Phase: VERDICT_ASSIGNMENT
  Condition: verdict object created
  Participants: Moderator
  Transition: → SYNTHESIS

Phase: SYNTHESIS
  Condition: synthesis text written
  Participants: Moderator
  Transition: → COMPLETE
```

---

## Multi-Axis Verdict Structure

```
VerdictDimension {
    methodological_soundness: int (1-5)
      ↳ Design quality, controls, execution
      ↳ Independent of hypothesis or conclusions

    evidence_strength: int (1-5)
      ↳ Data adequacy, statistical rigor
      ↳ Does data support specific claims made?

    novelty_value: int (1-5)
      ↳ Originality of question, method, or data
      ↳ Does this ask something new?

    scientific_contribution: int (1-5)
      ↳ Usefulness to field, even if wrong
      ↳ Does this move inquiry forward?

    risk_of_overreach: int (1-5)
      ↳ Gap between data and claims
      ↳ Are conclusions stated more strongly than supported?

    rationale: str
      ↳ Explicit justification for scores
      ↳ Must reference specific findings from debate
}
```

### Example Verdicts

**High-quality mainstream work:**
- Methodology: 5/5
- Evidence: 5/5
- Novelty: 3/5
- Contribution: 4/5
- Overreach: 1/5

**Novel but underpowered heterodox work:**
- Methodology: 3/5 (design OK, but small sample)
- Evidence: 2/5 (insufficient for strong claims)
- Novelty: 5/5 (asks new question)
- Contribution: 4/5 (valuable even if wrong)
- Overreach: 4/5 (claims too strong for data)

**Well-executed but incremental:**
- Methodology: 4/5
- Evidence: 4/5
- Novelty: 2/5 (minor extension)
- Contribution: 3/5
- Overreach: 2/5

---

## Principle Enforcement

### How Principles Are Applied

```
Agent Message:
  "This contradicts established theory, so methods must be flawed."
    ↓
Moderator Detection:
  - Violates Principle 3 (Anti-Orthodoxy Bias Control)
  - Violates Principle 1 (Methodological Neutrality)
    ↓
Moderator Intervention:
  "HALT. This reasoning violates our principles.

   You cannot assume methods are flawed because you
   disagree with conclusions.

   Provide SPECIFIC methodological critiques."
    ↓
Agent Correction:
  "The control group does not account for X, which could
   produce the observed effect independently."
    ↓
Audit Trail:
  principle_violations.append({
      "agent": "methodologist",
      "violation": "consensus_as_evidence",
      "timestamp": "...",
      "corrected": True,
  })
```

---

## Audit Trail Structure

Every review produces:

```json
{
  "paper": {
    "arxiv_id": "2401.12345",
    "title": "..."
  },
  "review_session": {
    "start_time": "2026-01-30T14:00:00",
    "end_time": "2026-01-30T14:15:23",
    "duration_seconds": 923
  },
  "phase_transitions": [
    {"phase": "initialization", "timestamp": "..."},
    {"phase": "claim_enumeration", "timestamp": "..."},
    ...
  ],
  "messages": [
    {
      "agent": "moderator",
      "phase": "initialization",
      "content": "...",
      "timestamp": "...",
      "references": []
    },
    ...
  ],
  "principle_violations": [
    {
      "agent": "skeptic",
      "principle": "anti_orthodoxy_bias",
      "violation_text": "...",
      "moderator_intervention": "...",
      "corrected": true
    }
  ],
  "verdict": { ... },
  "synthesis": "..."
}
```

---

## Technology Stack Summary

| Layer             | Technology                   | Justification                                  |
| ----------------- | ---------------------------- | ---------------------------------------------- |
| **Runtime**       | Python 3.14 + uv             | Modern, fast dependency management             |
| **Protocol**      | Model Context Protocol (MCP) | Standardized tool exposure, audit-friendly     |
| **Orchestration** | LangGraph                    | Explicit state machines, checkpointing         |
| **Agents**        | LangChain + LLM              | Composable, well-documented framework          |
| **Storage**       | JSON / PostgreSQL            | Simple for prototypes, scalable for production |
| **PDF Parsing**   | PyPDF2 / pdfplumber          | Standard tools with known limitations          |
| **arXiv API**     | arxiv Python library         | Official wrapper for arXiv API                 |

---

## Deployment Options

### Option 1: Local CLI

```bash
cd Science
uv run python -m scientific_judgment_mcp review --arxiv-id 2401.12345
```

### Option 2: MCP Server (for editors like Claude Desktop)

```json
// claude_desktop_config.json
{
  "mcpServers": {
    "scientific-judgment": {
      "command": "uv",
      "args": ["run", "python", "-m", "scientific_judgment_mcp.server"],
      "cwd": "/path/to/Science"
    }
  }
}
```

### Option 3: Web API (FastAPI)

```bash
uv run uvicorn api:app --host 0.0.0.0 --port 8000
```

### Option 4: Batch Processing (Celery)

```python
from celery import Celery

app = Celery("scientific_review", broker="redis://localhost")

@app.task
def review_paper_task(arxiv_id: str):
    return review_paper(arxiv_id)
```

---

## Security & Privacy

### Data Handling

- **Papers**: Public arXiv papers, no privacy concerns
- **Author Information**: Publicly available data only (ORCID, publications)
- **COI Data**: Facts only, no inference or speculation
- **Audit Trails**: Retain for reproducibility, anonymize on request

### API Security

- **Authentication**: JWT tokens or API keys
- **Rate Limiting**: Prevent abuse
- **Input Validation**: Sanitize arXiv IDs
- **Output Sanitization**: No injection attacks in generated reports

---

## Future Enhancements

1. **LaTeX Source Parsing**: Higher quality than PDF
2. **Figure/Table Analysis**: OCR or vision models
3. **Citation Graph Analysis**: Detect selective citing
4. **Replication Database Integration**: Check if others have replicated
5. **Pre-registration Checking**: Were hypotheses pre-registered?
6. **Statistical Re-analysis**: Re-run analyses on raw data
7. **Multi-Paper Meta-Analysis**: Synthesize across papers

---

**This architecture supports the system's mission:**

> Judge scientific papers fairly, rigorously, and transparently—
> rewarding methodological quality over conformity to consensus.

---

**Version**: 1.0.0
**Last Updated**: 2026-01-30
