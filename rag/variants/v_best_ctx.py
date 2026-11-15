"""best + contextual indexing: decomposition + hybrid + rerank over contextual chunks."""
from rag.variants.pipeline import Config, run

CFG = Config("best_ctx", decompose=True, hybrid=True, rerank=True, contextual=True)


def retrieve(job: dict, index, k: int = 5, **_) -> list[dict]:
    return run(job, index, k, CFG)
