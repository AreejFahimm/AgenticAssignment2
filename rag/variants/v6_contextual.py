"""V6 (indexing group): contextual retrieval. A context line (type, skills, industry, year) is prepended to every chunk before
embedding and BM25. Applied to the hybrid+rerank pipeline. NOTE: the silver gold labels are derived from the same skill metadata,
so this variant is partly circular on this corpus; the report says so."""
from rag.variants.pipeline import Config, run

CFG = Config("v6_contextual", hybrid=True, rerank=True, contextual=True)
CFG_DENSE = Config("v6_contextual_dense", contextual=True)


def retrieve(job: dict, index, k: int = 5, **_) -> list[dict]:
    return run(job, index, k, CFG)
