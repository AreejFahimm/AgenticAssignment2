"""Repo ingestion through the GitHub MCP server (A5/B1). UNTESTED SKELETON: needs a GitHub token and the server's tool names.

The corpora used for the committed results are local synthetic repos (data/personas/*/repos); this module shows the path for real repos:
tools are discovered at runtime (read-only: get_file_contents / search_code style tools), README + a bounded number of source files are
chunked with the same loaders and added to the persona index through PersonaIndex.add_items (incremental re-indexing).
"""
from __future__ import annotations

import os

from rag.ingest.loaders import chunk_text

GITHUB_MCP_URL = os.getenv("GITHUB_MCP_URL", "https://api.githubcopilot.com/mcp/")


async def ingest_repo(owner: str, repo: str, persona: str, token: str, max_files: int = 12) -> list[dict]:  # pragma: no cover
    from langchain_mcp_adapters.client import MultiServerMCPClient
    client = MultiServerMCPClient({"github": {"url": GITHUB_MCP_URL, "transport": "streamable_http", "headers": {"Authorization": f"Bearer {token}"}}})
    tools = {t.name: t for t in await client.get_tools()}
    getter = next((tools[n] for n in tools if "file" in n and "content" in n), None)
    if getter is None:
        raise RuntimeError(f"no file-content tool found on the GitHub MCP server; tools: {sorted(tools)}")
    items = []
    for path in ("README.md",):
        text = await getter.ainvoke({"owner": owner, "repo": repo, "path": path})
        for i, c in enumerate(chunk_text(str(text))):
            items.append(dict(evidence_id=f"{repo}:{path}#{i}", persona=persona, type="repo_readme", project_id=repo, text=c, skills=[],
                              industry=None, date=None, outcome=None))
    return items[: max_files * 4]
