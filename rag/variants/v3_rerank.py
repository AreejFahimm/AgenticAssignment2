"""V3 (retrieval group, required): cross-encoder reranking of a hybrid candidate pool."""
from rag.variants.pipeline import Config, run

CFG = Config("v3_rerank", hybrid=True, rerank=True)


def retrieve(job: dict, index, k: int = 5, **_) -> list[dict]:
    return run(job, index, k, CFG)
