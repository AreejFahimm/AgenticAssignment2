"""V2 (retrieval group, required): BM25 + dense fused with reciprocal rank fusion, on the whole job post."""
from rag.variants.pipeline import Config, run

CFG = Config("v2_hybrid", hybrid=True)


def retrieve(job: dict, index, k: int = 5, **_) -> list[dict]:
    return run(job, index, k, CFG)
