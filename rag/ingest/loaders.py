"""Ingestion loaders (B1): CV (PDF/MD), case-study Markdown, repo README + code, reviews, past proposals.

Every chunk carries metadata: persona, type, project, skills, date, client industry and (proposals) outcome.
GitHub repos are ingested through the GitHub MCP server in production (see docs/TOOLS.md); the local
loader below handles the synthetic persona corpora and any files the user uploads in the UI.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from rag.ingest.common_paths import PERSONAS_DIR

CHUNK = 600  # chars; items shorter than this stay whole
OVERLAP = 80


def chunk_text(text: str, size: int = CHUNK, overlap: int = OVERLAP) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text]
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + size])
        i += size - overlap
    return out


def load_pdf(path: Path) -> str:
    try:
        import pypdf  # optional dependency
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pip install pypdf to ingest PDF CVs") from e
    return "\n".join((p.extract_text() or "") for p in pypdf.PdfReader(str(path)).pages)


def load_markdown_case_study(path: Path, persona: str) -> list[dict]:
    t = path.read_text(encoding="utf-8")
    skills = re.search(r"\*\*Skills:\*\*\s*(.+)", t)
    ind = re.search(r"\*\*Industry:\*\*\s*(.+)", t)
    year = re.search(r"\*\*Year:\*\*\s*(\d{4})", t)
    return [dict(evidence_id=f"{path.stem}" + (f"#{i}" if i else ""), persona=persona, type="case_study", project_id=path.stem,
                 text=c, skills=[s.strip() for s in skills.group(1).split(",")] if skills else [],
                 industry=ind.group(1).strip() if ind else None, date=year.group(1) if year else None, outcome=None)
            for i, c in enumerate(chunk_text(t))]


def add_uploaded_file(path: Path, persona: str) -> list[dict]:
    """UI upload hook: returns new chunks to feed PersonaIndex.add_items() (incremental re-indexing)."""
    if path.suffix.lower() == ".pdf":
        text = load_pdf(path)
        return [dict(evidence_id=f"{path.stem}#{i}", persona=persona, type="cv", project_id=None, text=c, skills=[],
                     industry=None, date=None, outcome=None) for i, c in enumerate(chunk_text(text))]
    if path.suffix.lower() in (".md", ".txt"):
        return load_markdown_case_study(path, persona)
    raise ValueError(f"unsupported upload type: {path.suffix}")


def load_persona_evidence(persona: str) -> list[dict]:
    """Flat evidence index prepared by scripts/gen_personas.py (already item-level with metadata)."""
    p = PERSONAS_DIR / persona / "evidence.jsonl"
    items = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            e = json.loads(line)
            e["persona"] = persona
            items.append(e)
    return items


def load_proposals(persona: str) -> list[dict]:
    p = PERSONAS_DIR / persona / "proposals.jsonl"
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
