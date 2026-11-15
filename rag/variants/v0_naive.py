"""V0 (baseline, required): naive dense top-k cosine on the whole job post."""
from rag.variants.pipeline import Config, run

CFG = Config("v0_naive")


def retrieve(job: dict, index, k: int = 5, **_) -> list[dict]:
    return run(job, index, k, CFG)
