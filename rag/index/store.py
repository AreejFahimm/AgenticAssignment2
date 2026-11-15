"""Per-persona hybrid index: dense (fastembed, open model, CPU) + BM25. Incremental add (B1)."""
from __future__ import annotations

import hashlib
import re
from functools import lru_cache

import numpy as np
from rank_bm25 import BM25Okapi

from rag.ingest.common_paths import CACHE_DIR
from rag.ingest.loaders import load_persona_evidence, load_proposals

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
_TOK = re.compile(r"[a-z0-9\+\#\.]+")


def tokenize(t: str) -> list[str]:
    return _TOK.findall(t.lower())


@lru_cache(maxsize=1)
def embedder():
    from fastembed import TextEmbedding
    return TextEmbedding(EMBED_MODEL)


@lru_cache(maxsize=1)
def reranker():
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    return TextCrossEncoder(RERANK_MODEL)


def embed_docs(texts: list[str]) -> np.ndarray:
    v = np.array(list(embedder().embed(texts)), dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


@lru_cache(maxsize=20000)
def embed_query(q: str) -> np.ndarray:
    v = np.array(list(embedder().query_embed([q])), dtype=np.float32)[0]
    return v / np.linalg.norm(v)


def doc_text(e: dict, contextual: bool) -> str:
    """V6 contextual retrieval: a generated context line (type, skills, industry, year) is prepended to each chunk before
    embedding / BM25, so fragments keep their meaning and implied skills become matchable. The stored item text is unchanged."""
    if not contextual:
        return e["text"]
    ctx = f"[{e['type'].replace('_', ' ')}] skills: {', '.join(e.get('skills') or []) or 'n/a'}; industry: {e.get('industry') or 'n/a'}; year: {e.get('date') or 'n/a'}."
    return f"{ctx} {e['text']}"


class PersonaIndex:
    def __init__(self, persona: str, items: list[dict], outcome_by_project: dict[str, float] | None = None, contextual: bool = False):
        self.persona = persona
        self.contextual = contextual
        self.items: list[dict] = []
        self.emb = np.zeros((0, 384), dtype=np.float32)
        self.outcome_by_project = outcome_by_project or {}
        self.add_items(items)

    # -- incremental re-indexing (user uploads new work in the UI) --
    def add_items(self, new: list[dict]) -> None:
        if not new:
            return
        texts = [doc_text(e, self.contextual) for e in new]
        self.emb = np.vstack([self.emb, self._embed_cached(texts)])
        self.items += new
        self.bm25 = BM25Okapi([tokenize(doc_text(e, self.contextual)) for e in self.items])

    def _embed_cached(self, texts: list[str]) -> np.ndarray:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        key = hashlib.md5(("|".join(texts) + EMBED_MODEL).encode()).hexdigest()  # contextual docs differ -> separate cache entry
        f = CACHE_DIR / f"{key}.npy"
        if f.exists():
            return np.load(f)
        v = embed_docs(texts)
        np.save(f, v)
        return v

    # -- primitives used by variants --
    def dense(self, query: str, k: int, types: set[str] | None = None) -> list[tuple[int, float]]:
        s = self.emb @ embed_query(query)
        return self._top(s, k, types)

    def bm25_search(self, query: str, k: int, types: set[str] | None = None) -> list[tuple[int, float]]:
        return self._top(np.array(self.bm25.get_scores(tokenize(query))), k, types)

    def _top(self, scores: np.ndarray, k: int, types: set[str] | None) -> list[tuple[int, float]]:
        order = np.argsort(-scores)
        out = []
        for i in order:
            if types and self.items[i]["type"] not in types:
                continue
            out.append((int(i), float(scores[i])))
            if len(out) >= k:
                break
        return out


@lru_cache(maxsize=16)
def get_index(persona: str, contextual: bool = False) -> PersonaIndex:
    outcomes: dict[str, float] = {}
    for p in load_proposals(persona):
        w = {"won": 1.0, "replied": 0.5, "ignored": 0.0}[p["outcome"]]
        for pid in p.get("cited_project_ids", []):
            outcomes[pid] = max(outcomes.get(pid, 0.0), w)
    return PersonaIndex(persona, load_persona_evidence(persona), outcomes, contextual)
