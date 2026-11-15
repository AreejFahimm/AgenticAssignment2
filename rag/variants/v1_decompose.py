"""V1 (query group, required): one dense retrieval per extracted requirement, merged with RRF."""
from rag.variants.pipeline import Config, run

CFG = Config("v1_decompose", decompose=True)


def retrieve(job: dict, index, k: int = 5, **_) -> list[dict]:
    return run(job, index, k, CFG)
