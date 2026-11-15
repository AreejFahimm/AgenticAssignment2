"""Factory: retrieval variant chosen by config (R6: the shipped design is picked by evaluation)."""
from __future__ import annotations

import importlib

VARIANTS = {
    "v0": "rag.variants.v0_naive", "v1": "rag.variants.v1_decompose", "v2": "rag.variants.v2_hybrid",
    "v3": "rag.variants.v3_rerank", "v4": "rag.variants.v4_outcome", "v8": "rag.variants.v8_corrective",
    "v6": "rag.variants.v6_contextual", "best": "rag.variants.v_best", "best_ctx": "rag.variants.v_best_ctx", "ship": "rag.variants.v_ship",
}


def get_retriever(name: str):
    return importlib.import_module(VARIANTS[name]).retrieve
