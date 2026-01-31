#!/usr/bin/env python3
"""MCP Server for Scientific Paper Judgment System

This server provides tools for:
- System diagnostics
- Paper ingestion (arXiv)
- Author research
- COI analysis
- Evidence extraction
"""

import asyncio
import json
import os
import platform
import sys
from datetime import datetime
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)

from .tools import arxiv, author_research

# Initialize MCP server
app = Server("scientific-judgment-mcp")


# ============================================================================
# PHASE 1: DIAGNOSTIC TOOLS
# ============================================================================


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="ping",
            description="Simple health check that returns server status",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="env_info",
            description="Return environment and system information",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="tool_inventory",
            description="List all available tools with descriptions and capabilities",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="fetch_arxiv_paper",
            description="Fetch and extract content from an arXiv paper",
            inputSchema={
                "type": "object",
                "properties": {
                    "arxiv_id": {
                        "type": "string",
                        "description": "arXiv identifier (e.g., '2401.12345')",
                    },
                },
                "required": ["arxiv_id"],
            },
        ),
        Tool(
            name="research_author",
            description="Research author background and publication history",
            inputSchema={
                "type": "object",
                "properties": {
                    "author_name": {
                        "type": "string",
                        "description": "Name of the author to research",
                    },
                    "paper_title": {
                        "type": "string",
                        "description": "Title of the paper (for context)",
                    },
                },
                "required": ["author_name", "paper_title"],
            },
        ),
        Tool(
            name="analyze_coi",
            description="Analyze conflicts of interest for a paper (surfacing, not dismissal)",
            inputSchema={
                "type": "object",
                "properties": {
                    "authors": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of author names",
                    },
                    "paper_title": {
                        "type": "string",
                        "description": "Paper title",
                    },
                    "paper_metadata": {
                        "type": "object",
                        "description": "Additional paper metadata",
                    },
                },
                "required": ["authors", "paper_title"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool invocation."""

    if name == "ping":
        return [
            TextContent(
                type="text",
                text=json.dumps({
                    "status": "operational",
                    "server": "scientific-judgment-mcp",
                    "version": "0.1.0",
                    "timestamp": datetime.now().isoformat(),
                }, indent=2),
            )
        ]

    elif name == "env_info":
        env_data = {
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "processor": platform.processor(),
            },
            "python": {
                "version": platform.python_version(),
                "implementation": platform.python_implementation(),
                "executable": sys.executable,
            },
            "environment": {
                "cwd": os.getcwd(),
                "user": os.environ.get("USER", "unknown"),
                "home": os.environ.get("HOME", "unknown"),
            },
            "server": {
                "name": "scientific-judgment-mcp",
                "version": "0.1.0",
                "protocol": "MCP (Model Context Protocol)",
            },
        }
        return [
            TextContent(
                type="text",
                text=json.dumps(env_data, indent=2),
            )
        ]

    elif name == "tool_inventory":
        inventory = {
            "server": "scientific-judgment-mcp",
            "version": "0.1.0",
            "tool_categories": {
                "diagnostic": {
                    "description": "Health checks and system information",
                    "tools": [
                        {
                            "name": "ping",
                            "purpose": "Health check",
                            "inputs": "none",
                            "outputs": "Status and timestamp",
                        },
                        {
                            "name": "env_info",
                            "purpose": "System environment details",
                            "inputs": "none",
                            "outputs": "Platform, Python, environment variables",
                        },
                        {
                            "name": "tool_inventory",
                            "purpose": "List all available tools",
                            "inputs": "none",
                            "outputs": "Tool catalog with descriptions",
                        },
                    ],
                },
                "arxiv": {
                    "description": "Paper ingestion and extraction (PHASE 5)",
                    "status": "implemented",
                    "tools": [
                        "fetch_arxiv_paper",
                    ],
                },
                "author_research": {
                    "description": "Author background and COI analysis (PHASE 4)",
                    "status": "partial",
                    "tools": [
                        "research_author",
                        "analyze_coi",
                    ],
                },
                "judgment": {
                    "description": "Core evaluation and deliberation (PHASE 6)",
                    "status": "not_yet_implemented",
                    "planned_tools": [
                        "enumerate_claims",
                        "evaluate_methodology",
                        "assess_evidence",
                        "check_progress_value",
                    ],
                },
            },
            "principles": {
                "reference": "See SCIENTIFIC_PRINCIPLES.md",
                "key_tenets": [
                    "Methodological neutrality",
                    "Separation of concerns",
                    "Anti-orthodoxy bias control",
                    "COI awareness without dismissal",
                    "Progress-of-science test",
                ],
            },
        }
        return [
            TextContent(
                type="text",
                text=json.dumps(inventory, indent=2),
            )
        ]

    elif name == "fetch_arxiv_paper":
        arxiv_id = (arguments or {}).get("arxiv_id")
        if not arxiv_id:
            return [TextContent(type="text", text=json.dumps({"error": "Missing arxiv_id"}, indent=2))]

        paper = await arxiv.mcp_fetch_arxiv_paper(str(arxiv_id))
        return [TextContent(type="text", text=json.dumps(paper, indent=2))]

    elif name == "research_author":
        author_name = (arguments or {}).get("author_name")
        paper_title = (arguments or {}).get("paper_title")
        if not author_name or not paper_title:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": "Missing author_name or paper_title"}, indent=2),
                )
            ]

        profile = await author_research.mcp_research_author_history(str(author_name), str(paper_title))
        return [TextContent(type="text", text=json.dumps(profile, indent=2))]

    elif name == "analyze_coi":
        authors = (arguments or {}).get("authors")
        paper_title = (arguments or {}).get("paper_title")
        paper_metadata = (arguments or {}).get("paper_metadata") or {}
        if not authors or not paper_title:
            return [TextContent(type="text", text=json.dumps({"error": "Missing authors or paper_title"}, indent=2))]

        report = await author_research.mcp_analyze_coi(list(authors), str(paper_title), dict(paper_metadata))
        return [TextContent(type="text", text=json.dumps(report, indent=2))]

    else:
        return [
            TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Unknown tool: {name}",
                    "available_tools": [
                        "ping",
                        "env_info",
                        "tool_inventory",
                        "fetch_arxiv_paper",
                        "research_author",
                        "analyze_coi",
                    ],
                }, indent=2),
            )
        ]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
