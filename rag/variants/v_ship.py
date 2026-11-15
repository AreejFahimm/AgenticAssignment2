"""SHIPPED variant (chosen by ablation, evals/results/ablation.json): requirement decomposition + hybrid BM25/dense (RRF) over CONTEXTUAL chunks,
WITHOUT the cross-encoder. On this corpus the MiniLM cross-encoder REDUCED recall (best - rerank beat best) and cost ~1.5 s/job, so it is not shipped.
Caveat (also in the report): contextual chunks expose item skill metadata, and the silver gold labels are derived from that metadata, so the gain is partly circular."""
from rag.variants.pipeline import Config, run

CFG = Config("ship", decompose=True, hybrid=True, rerank=False, contextual=True)


def retrieve(job: dict, index, k: int = 5, **_) -> list[dict]:
    return run(job, index, k, CFG)
