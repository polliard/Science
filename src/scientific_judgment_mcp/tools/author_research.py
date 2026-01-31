"""Author research and COI analysis tools (Phase 4, expanded in Phase 9.2).

Objective:
- Surface factual author context without guilt-by-association.
- Separate VERIFIED FACTS vs INFERRED INCENTIVES vs SPECULATION.

Integrations (read-only):
- ORCID (identity and public works list)
- PubMed (biomedical publication presence)
- NIH RePORTER (funding presence)
"""

import asyncio
import os
from typing import Optional, Any
from datetime import datetime
from xml.etree import ElementTree

import httpx
from pydantic import BaseModel, Field


class AuthorProfile(BaseModel):
    """Profile of a paper author."""

    name: str
    affiliations: list[str] = Field(default_factory=list)
    email: Optional[str] = None
    orcid: Optional[str] = None


class FundingSource(BaseModel):
    """Identified funding source."""

    funder: str
    grant_number: Optional[str] = None
    amount: Optional[str] = None
    source: str  # Where this information was found


class Affiliation(BaseModel):
    """Institutional affiliation."""

    institution: str
    department: Optional[str] = None
    country: Optional[str] = None


class PriorPublicPosition(BaseModel):
    """Prior public advocacy or position."""

    topic: str
    position: str
    source: str
    date: Optional[str] = None


class COIReport(BaseModel):
    """Conflict of interest analysis report.

    CRITICAL: This is INFORMATION, not DISQUALIFICATION.
    """

    authors: list[AuthorProfile]
    funding_sources: list[FundingSource]
    affiliations: list[Affiliation]
    prior_positions: list[PriorPublicPosition]

    financial_coi: str = Field(
        description="Summary of financial conflicts (factual only)"
    )
    institutional_coi: str = Field(
        description="Summary of institutional interests (factual only)"
    )
    career_incentives: str = Field(
        description="Career or reputational incentives identified (factual only)"
    )
    ideological_positions: str = Field(
        description="Prior public advocacy on related topics (factual only)"
    )

    absence_note: str = Field(
        description="Note when no significant conflicts are found"
    )

    author_context_appendix: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured appendix: facts vs inference vs speculation (Phase 9.2)"
    )

    timestamp: datetime = Field(default_factory=datetime.now)


async def research_author_from_paper(author_name: str, paper_title: str) -> AuthorProfile:
    """Research an author based on their name and paper.

    Args:
        author_name: Name of the author
        paper_title: Title of the paper (for context)

    Returns:
        Basic author profile

    Note:
        Real implementation would query:
        - ORCID
        - Google Scholar
        - Semantic Scholar
        - PubMed
    """
    profile = AuthorProfile(
        name=author_name,
        affiliations=[],
        orcid=None,
    )

    # Best-effort ORCID match (public data; may be ambiguous)
    try:
        orcid_hits = await orcid_search_people(author_name)
        if len(orcid_hits) == 1:
            profile.orcid = orcid_hits[0].get("orcid")
        elif len(orcid_hits) > 1:
            # Ambiguous: do not guess.
            profile.affiliations.append("[ORCID match ambiguous: multiple candidates]")
        else:
            profile.affiliations.append("[No ORCID record found via public search]")
    except Exception:
        profile.affiliations.append("[ORCID lookup failed/unavailable]")

    if not profile.affiliations:
        profile.affiliations.append("[Affiliation not resolved from public sources]")

    return profile


def _name_query(author_name: str) -> str:
    parts = [p for p in author_name.replace(",", " ").split() if p.strip()]
    if not parts:
        return author_name
    if len(parts) == 1:
        return parts[0]
    given = parts[0]
    family = parts[-1]
    # ORCID Lucene-ish query
    return f'given-names:"{given}" AND family-name:"{family}"'


async def orcid_search_people(author_name: str, *, timeout_s: float = 10.0) -> list[dict[str, str]]:
    """Search ORCID public registry for a person.

    Returns list of candidates: {"orcid": "0000-...", "display": "..."}.

    NOTE: Name-based matching is inherently ambiguous; do not treat as identity proof.
    """

    query = _name_query(author_name)
    url = "https://pub.orcid.org/v3.0/search"
    headers = {"Accept": "application/json"}

    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
        resp = await client.get(url, params={"q": query, "rows": 5}, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    results = []
    for r in data.get("result", []) or []:
        orcid = (((r.get("orcid-identifier") or {}).get("path")) or "").strip()
        if not orcid:
            continue
        results.append({"orcid": orcid, "display": author_name})
    return results


async def pubmed_search_author(author_name: str, *, max_results: int = 5, timeout_s: float = 10.0) -> dict[str, Any]:
    """Search PubMed via NCBI E-utilities.

    Returns facts: count + example PMIDs + titles (best-effort).
    """

    term = f"{author_name}[Author]"
    esearch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    esummary = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
        r1 = await client.get(esearch, params={"db": "pubmed", "term": term, "retmax": max_results})
        r1.raise_for_status()
        root = ElementTree.fromstring(r1.text)
        count_text = root.findtext("Count") or "0"
        pmids = [e.text for e in root.findall(".//IdList/Id") if e.text]

        titles: list[str] = []
        if pmids:
            r2 = await client.get(esummary, params={"db": "pubmed", "id": ",".join(pmids)})
            r2.raise_for_status()
            root2 = ElementTree.fromstring(r2.text)
            for docsum in root2.findall(".//DocSum"):
                for item in docsum.findall("Item"):
                    if item.get("Name") == "Title" and item.text:
                        titles.append(item.text)

    return {
        "count": int(count_text) if count_text.isdigit() else 0,
        "example_pmids": pmids,
        "example_titles": titles,
        "source": "pubmed_eutils",
    }


async def nih_reporter_search_pi(author_name: str, *, timeout_s: float = 10.0) -> dict[str, Any]:
    """Search NIH RePORTER v2 for projects associated with a PI name (best-effort)."""

    url = "https://api.reporter.nih.gov/v2/projects/search"
    payload = {
        "criteria": {"pi_names": [author_name]},
        "offset": 0,
        "limit": 5,
        "sort_field": "project_start_date",
        "sort_order": "desc",
    }

    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    projects = data.get("results", []) or []
    sample = []
    for p in projects[:5]:
        sample.append({
            "project_number": p.get("project_num"),
            "project_title": p.get("project_title"),
            "agency": p.get("agency"),
        })

    return {
        "count": int(data.get("meta", {}).get("total", 0) or 0),
        "sample_projects": sample,
        "source": "nih_reporter_v2",
    }


async def build_author_context_appendix(
    *,
    authors: list[str],
    paper_title: str,
    topic_hint: str | None = None,
) -> dict[str, Any]:
    """Create a structured Author Context Appendix.

    Rules enforced:
    - Funding ≠ bias
    - Affiliation ≠ motive
    - Facts vs inference vs speculation separated
    - Missing data explicitly stated
    """

    appendix: dict[str, Any] = {
        "verified_facts": [],
        "inferred_incentives": [],
        "speculation": [],
        "declared_conflicts": [],
        "authors": [],
        "notable_absences": [],
        "sources": [],
    }

    topic = topic_hint or paper_title

    for author in authors:
        author_block: dict[str, Any] = {
            "name": author,
            "orcid_candidates": [],
            "pubmed": None,
            "nih_reporter": None,
            "missing_data": [],
        }

        # ORCID
        try:
            hits = await orcid_search_people(author)
            author_block["orcid_candidates"] = hits
            appendix["sources"].append("orcid_public_api")
            if not hits:
                author_block["missing_data"].append("No ORCID record found via public search.")
        except Exception as exc:
            author_block["missing_data"].append(f"ORCID lookup failed: {type(exc).__name__}.")

        # PubMed
        try:
            pub = await pubmed_search_author(author)
            author_block["pubmed"] = pub
            appendix["sources"].append("pubmed_eutils")
        except Exception as exc:
            author_block["missing_data"].append(f"PubMed lookup failed: {type(exc).__name__}.")

        # NIH RePORTER
        try:
            nih = await nih_reporter_search_pi(author)
            author_block["nih_reporter"] = nih
            appendix["sources"].append("nih_reporter_v2")
        except Exception as exc:
            author_block["missing_data"].append(f"NIH RePORTER lookup failed: {type(exc).__name__}.")

        appendix["authors"].append(author_block)

    # Missing-data rollup (explicitly stated)
    if not appendix["sources"]:
        appendix["notable_absences"].append("No external author enrichment sources were reachable.")

    # Inference rules: we only infer generic incentives, not accusations.
    appendix["inferred_incentives"].append(
        "All researchers face generic incentives (career advancement, publication pressure). This is not evidence of bias."
    )

    return appendix


async def find_funding_sources(paper_metadata: dict) -> list[FundingSource]:
    """Identify funding sources for a paper.

    Args:
        paper_metadata: Paper metadata including acknowledgments

    Returns:
        List of identified funding sources

    Note:
        Real implementation would:
        - Parse acknowledgments section
        - Query funding databases (NIH Reporter, NSF, etc.)
        - Check institutional funding disclosures
    """
    # Placeholder
    return [
        FundingSource(
            funder="[Funding source research not yet implemented]",
            source="paper_acknowledgments",
        )
    ]


async def check_affiliations(authors: list[str]) -> list[Affiliation]:
    """Check institutional affiliations for authors.

    Args:
        authors: List of author names

    Returns:
        List of institutional affiliations

    Note:
        Real implementation would query institutional databases
    """
    # Placeholder
    return [
        Affiliation(
            institution="[Affiliation check not yet implemented]",
        )
    ]


async def search_prior_public_positions(author: str, topic: str) -> list[PriorPublicPosition]:
    """Search for author's prior public positions on related topics.

    Args:
        author: Author name
        topic: Topic area to search

    Returns:
        List of identified public positions

    Note:
        Real implementation would search:
        - News articles
        - Op-eds
        - Public talks/presentations
        - Social media (with caution)
        - Policy statements

        CRITICAL: Facts only, no inference.
    """
    # Placeholder
    return [
        PriorPublicPosition(
            topic=topic,
            position="[Prior position research not yet implemented]",
            source="placeholder",
        )
    ]


async def analyze_conflicts_of_interest(
    authors: list[str],
    paper_title: str,
    paper_metadata: dict,
) -> COIReport:
    """Comprehensive COI analysis for a paper.

    Args:
        authors: List of author names
        paper_title: Paper title
        paper_metadata: Full paper metadata

    Returns:
        COI analysis report

    CRITICAL PRINCIPLES:
    - Surfacing ≠ Dismissal
    - Facts only, no moralizing
    - Must note absence of conflicts when applicable
    - Industry funding is INFORMATION, not DISQUALIFICATION
    """
    # Research authors
    author_profiles = await asyncio.gather(*[
        research_author_from_paper(author, paper_title)
        for author in authors
    ])

    # Find funding
    funding_sources = await find_funding_sources(paper_metadata)

    # Check affiliations
    affiliations = await check_affiliations(authors)

    # Search prior positions
    prior_positions = []
    for author in authors:
        positions = await search_prior_public_positions(author, paper_title)
        prior_positions.extend(positions)

    # Construct report (placeholder analysis)
    appendix = {}
    try:
        appendix = await build_author_context_appendix(authors=authors, paper_title=paper_title)
    except Exception:
        appendix = {
            "notable_absences": ["Author enrichment failed or was unavailable."],
            "sources": [],
        }

    report = COIReport(
        authors=author_profiles,
        funding_sources=funding_sources,
        affiliations=affiliations,
        prior_positions=prior_positions,
        financial_coi="[COI analysis not yet fully implemented]",
        institutional_coi="[COI analysis not yet fully implemented]",
        career_incentives="[COI analysis not yet fully implemented]",
        ideological_positions="[COI analysis not yet fully implemented]",
        absence_note="Full COI analysis pending implementation. Placeholder data shown.",
        author_context_appendix=appendix,
    )

    return report


# ============================================================================
# MCP TOOL INTEGRATION
# ============================================================================

async def mcp_research_author_history(author_name: str, paper_title: str) -> dict:
    """MCP tool: Research author publication history and background.

    Returns:
        Author profile dictionary
    """
    profile = await research_author_from_paper(author_name, paper_title)
    return profile.model_dump()


async def mcp_analyze_coi(authors: list[str], paper_title: str, paper_metadata: dict) -> dict:
    """MCP tool: Analyze conflicts of interest.

    Returns:
        COI report dictionary
    """
    report = await analyze_conflicts_of_interest(authors, paper_title, paper_metadata)
    return report.model_dump()
