"""V4 (ranking group): hybrid retrieval with a boost for evidence from proposals that won or got replies."""
from rag.variants.pipeline import Config, run

CFG = Config("v4_outcome", hybrid=True, outcome=True)


def retrieve(job: dict, index, k: int = 5, **_) -> list[dict]:
    return run(job, index, k, CFG)
