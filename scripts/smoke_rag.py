import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rag.index.store import get_index  # noqa: E402
from rag.retriever import get_retriever  # noqa: E402

t = time.time()
idx = get_index("data_analyst")
print("index", len(idx.items), round(time.time() - t, 1))
p = Path(__file__).resolve().parents[1] / "evals/datasets/dev_data_analyst.jsonl"
job = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()][0]
print(job["title"], job["required_skills"], job["gold"]["relevant_evidence"])
for v in ["v0", "v1", "v2", "v3", "v4", "v8", "best"]:
    t = time.time()
    h = get_retriever(v)(job, idx, 5)
    print(v, [x["evidence_id"] for x in h], round(time.time() - t, 2))
