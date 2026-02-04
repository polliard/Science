"""arXiv paper ingestion and extraction tools (Phase 5).

Tools for downloading papers, extracting metadata and content,
normalizing into PaperContext for review.
"""

import re
import os
from typing import Optional
from pathlib import Path

import httpx
import certifi
from PyPDF2 import PdfReader
from pydantic import BaseModel

from scientific_judgment_mcp.orchestration import PaperContext


def _ensure_ca_bundle() -> None:
    """Ensure SSL certificate bundle is available.

    Some Python/uv environments on macOS can lack a configured trust store.
    Prefer the OS trust store when available (truststore), and fall back to
    certifi when needed.
    """

    try:
        import truststore

        truststore.inject_into_ssl()
        return
    except Exception:
        ca = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", ca)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca)


def _insecure_ssl_enabled() -> bool:
    return os.environ.get("SCIJUDGE_INSECURE_SSL", "").strip() in {"1", "true", "yes"}


def _http_verify_setting():
    # Prefer explicit cert bundle; allow opt-in insecure mode for constrained environments.
    if _insecure_ssl_enabled():
        return False
    custom = os.environ.get("SCIJUDGE_CA_BUNDLE")
    if custom and custom.strip():
        return custom.strip()
    try:
        import truststore  # noqa: F401

        return True
    except Exception:
        return certifi.where()


async def _http_get_text(url: str, *, params: dict | None = None) -> str:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, verify=_http_verify_setting()) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.text


async def _http_get_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, verify=_http_verify_setting()) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


class ArxivMetadata(BaseModel):
    """Extracted metadata from arXiv."""

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    published: str
    updated: str
    categories: list[str]
    pdf_url: str
    comment: Optional[str] = None


async def fetch_arxiv_metadata(arxiv_id: str) -> ArxivMetadata:
    """Fetch metadata for an arXiv paper.

    Args:
        arxiv_id: arXiv identifier (e.g., "2401.12345" or "arxiv:2401.12345")

    Returns:
        Extracted metadata
    """
    # Normalize arXiv ID
    arxiv_id = arxiv_id.replace("arxiv:", "").strip()

    _ensure_ca_bundle()

    # Query arXiv Atom feed directly for better control over TLS settings.
    url = "https://export.arxiv.org/api/query"
    text = await _http_get_text(url, params={"id_list": arxiv_id})

    # Atom namespace
    import xml.etree.ElementTree as ET

    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(text)
    entry = root.find("a:entry", ns)
    if entry is None:
        raise ValueError(f"arXiv paper not found: {arxiv_id}")

    title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
    abstract = (entry.findtext("a:summary", default="", namespaces=ns) or "").strip()
    published = (entry.findtext("a:published", default="", namespaces=ns) or "").strip()
    updated = (entry.findtext("a:updated", default="", namespaces=ns) or "").strip()

    authors = []
    for a in entry.findall("a:author", ns):
        name = (a.findtext("a:name", default="", namespaces=ns) or "").strip()
        if name:
            authors.append(name)

    categories = []
    for c in entry.findall("a:category", ns):
        term = (c.attrib.get("term") or "").strip()
        if term:
            categories.append(term)

    pdf_url = ""
    for link in entry.findall("a:link", ns):
        if link.attrib.get("title") == "pdf" and link.attrib.get("href"):
            pdf_url = link.attrib["href"].strip()
            break
    if not pdf_url:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    return ArxivMetadata(
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        abstract=abstract,
        published=published,
        updated=updated,
        categories=categories,
        pdf_url=pdf_url,
        comment=None,
    )


async def download_arxiv_pdf(arxiv_id: str, output_dir: Path) -> Path:
    """Download PDF for an arXiv paper.

    Args:
        arxiv_id: arXiv identifier
        output_dir: Directory to save PDF

    Returns:
        Path to downloaded PDF
    """
    arxiv_id = arxiv_id.replace("arxiv:", "").strip()

    _ensure_ca_bundle()

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / f"{arxiv_id}.pdf"

    metadata = await fetch_arxiv_metadata(arxiv_id)
    pdf_bytes = await _http_get_bytes(metadata.pdf_url)
    pdf_path.write_bytes(pdf_bytes)

    return pdf_path


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text content from PDF.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Extracted text

    Note:
        PDF extraction is imperfect. Results may have:
        - Formatting issues
        - Missing or garbled text
        - Incorrect section detection
    """
    reader = PdfReader(pdf_path)

    text_parts = []
    for page in reader.pages:
        text_parts.append(page.extract_text())

    return "\n\n".join(text_parts)


def extract_paper_sections(full_text: str) -> dict[str, str]:
    """Extract common paper sections from text.

    Args:
        full_text: Full paper text from PDF

    Returns:
        Dictionary of section name -> content

    Note:
        Section detection is heuristic and may be inaccurate.
    """
    sections = {}

    # Common section headers (case-insensitive patterns)
    patterns = {
        "introduction": r"\n\s*(?:1\.?\s*)?Introduction\s*\n",
        "methods": r"\n\s*(?:\d+\.?\s*)?(?:Methods?|Methodology|Experimental Setup)\s*\n",
        "results": r"\n\s*(?:\d+\.?\s*)?Results?\s*\n",
        "discussion": r"\n\s*(?:\d+\.?\s*)?Discussion\s*\n",
        "conclusion": r"\n\s*(?:\d+\.?\s*)?Conclusions?\s*\n",
        "limitations": r"\n\s*(?:\d+\.?\s*)?Limitations?\s*\n",
    }

    for section_name, pattern in patterns.items():
        matches = list(re.finditer(pattern, full_text, re.IGNORECASE))
        if matches:
            start = matches[0].end()
            # Find next section or end of document
            next_section = None
            for other_pattern in patterns.values():
                other_matches = list(re.finditer(other_pattern, full_text[start:], re.IGNORECASE))
                if other_matches:
                    if next_section is None or other_matches[0].start() < next_section:
                        next_section = other_matches[0].start()

            if next_section:
                sections[section_name] = full_text[start:start + next_section].strip()
            else:
                sections[section_name] = full_text[start:start + 2000].strip()  # Cap length

    return sections


def _build_full_text_excerpt(full_text: str, *, max_chars: int = 45000) -> str:
    """Build a targeted excerpt for downstream quote grounding.

    This avoids placing the entire (often huge) extracted PDF text into prompts.
    Heuristic: take a head snippet plus windows around systematic-review keywords.
    """

    text = (full_text or "").strip()
    if not text:
        return ""

    head = text[:12000]
    if len(head) >= max_chars:
        return head[:max_chars]

    keywords = [
        "systematic review",
        "prisma",
        "inclusion criteria",
        "exclusion criteria",
        "search strategy",
        "search string",
        "database",
        "databases",
        "screening",
        "risk of bias",
        "quality assessment",
        "data extraction",
        "eligibility",
        "meta-analysis",
    ]

    windows: list[str] = []
    lower = text.lower()
    for kw in keywords:
        idx = lower.find(kw)
        if idx < 0:
            continue
        start = max(0, idx - 1200)
        end = min(len(text), idx + 2200)
        win = text[start:end].strip()
        if win and win not in windows:
            windows.append(win)
        if sum(len(w) for w in windows) + len(head) > max_chars:
            break

    out = head
    for w in windows:
        if len(out) + 3 + len(w) > max_chars:
            break
        out += "\n\n---\n" + w
    return out[:max_chars]


def extract_claims_from_abstract(abstract: str) -> list[str]:
    """Heuristically extract claims from abstract.

    Args:
        abstract: Paper abstract

    Returns:
        List of potential claims

    Note:
        This is a simple heuristic. Real implementation would use
        LLM-based claim extraction.
    """
    # Split into sentences
    sentences = re.split(r'[.!?]+', abstract)

    # Look for claim indicators
    claim_indicators = [
        "we show",
        "we demonstrate",
        "we find",
        "we prove",
        "we establish",
        "results show",
        "results indicate",
        "evidence suggests",
    ]

    claims = []
    for sentence in sentences:
        sentence = sentence.strip()
        if any(indicator in sentence.lower() for indicator in claim_indicators):
            claims.append(sentence)

    return claims if claims else [abstract]  # Fall back to full abstract


async def ingest_arxiv_paper(arxiv_id: str, download_dir: Optional[Path] = None) -> PaperContext:
    """Complete ingestion pipeline for an arXiv paper.

    Args:
        arxiv_id: arXiv identifier
        download_dir: Optional directory for PDF download

    Returns:
        Normalized PaperContext for review
    """
    if download_dir is None:
        download_dir = Path("/tmp/arxiv_papers")

    # Fetch metadata
    metadata = await fetch_arxiv_metadata(arxiv_id)

    # Download PDF
    pdf_path = await download_arxiv_pdf(arxiv_id, download_dir)

    # Extract text
    full_text = extract_text_from_pdf(pdf_path)

    excerpt = _build_full_text_excerpt(full_text)

    # Extract sections
    sections = extract_paper_sections(full_text)

    # Extract claims
    claims = extract_claims_from_abstract(metadata.abstract)

    # Create PaperContext
    paper_context = PaperContext(
        arxiv_id=metadata.arxiv_id,
        title=metadata.title,
        authors=metadata.authors,
        abstract=metadata.abstract,
        claims=claims,
        methods=sections.get("methods", ""),
        results=sections.get("results", ""),
        limitations=sections.get("limitations", "").split("\n") if "limitations" in sections else [],
        full_text_excerpt=excerpt,
    )

    if _insecure_ssl_enabled():
        paper_context.limitations.append(
            "TLS certificate verification was DISABLED (SCIJUDGE_INSECURE_SSL=1) to fetch arXiv content in this environment."
        )

    return paper_context


# ============================================================================
# MCP TOOL INTEGRATION
# ============================================================================

async def mcp_fetch_arxiv_paper(arxiv_id: str) -> dict:
    """MCP tool: Fetch arXiv paper metadata and content.

    Returns:
        Dictionary representation of PaperContext
    """
    paper = await ingest_arxiv_paper(arxiv_id)
    return paper.model_dump()
