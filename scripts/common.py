"""Shared helpers for the GigBid data pipeline (provenance, masking, taxonomy, seeds)."""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
PERSONAS = ROOT / "data" / "personas"
DATASETS = ROOT / "evals" / "datasets"
RESULTS = ROOT / "evals" / "results"
SEED = 4016

# Provenance values: every record carries one. Never mix without it.
REAL = "real"                 # real:<kaggle slug>
REAL_MOD = "real_modified"    # real post edited by us (scam / injection / duplicate)
SYNTH = "synthetic"           # synthetic:<generator>:<seed>

PERSONA_IDS = ["ai_ml_engineer", "fullstack_web_dev", "data_analyst"]

# Skill taxonomy per persona. Used for skill extraction, persona filtering, fit gold labels.
PERSONA_SKILLS: dict[str, list[str]] = {
    "ai_ml_engineer": [
        "python", "pytorch", "tensorflow", "scikit-learn", "nlp", "llm", "langchain", "rag",
        "computer vision", "machine learning", "deep learning", "mlops", "fastapi", "docker",
        "huggingface", "classification", "time series", "recommendation", "openai", "chatbot",
    ],
    "fullstack_web_dev": [
        "react", "next.js", "typescript", "javascript", "node.js", "django", "flask", "postgresql",
        "mongodb", "tailwind", "rest api", "graphql", "aws", "docker", "stripe", "html", "css",
        "vue", "wordpress", "shopify",
    ],
    "data_analyst": [
        "sql", "excel", "power bi", "tableau", "python", "pandas", "data visualization",
        "google analytics", "data cleaning", "dashboard", "looker", "statistics", "etl", "dbt",
        "bigquery", "a/b testing", "reporting", "google sheets", "r", "web scraping",
    ],
}
ALL_SKILLS = sorted({s for v in PERSONA_SKILLS.values() for s in v})

CATEGORY_RULES = [  # (category, regex)
    ("ai_ml", r"machine learning|deep learning|nlp|llm|chatbot|pytorch|tensorflow|computer vision|rag\b|openai"),
    ("web_dev", r"react|next\.js|django|flask|node\.js|website|web app|frontend|backend|wordpress|shopify"),
    ("data_analytics", r"sql|power bi|tableau|dashboard|excel|data analy|reporting|etl|looker"),
]

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{8,}\d)(?!\d)")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def mask_pii(text: str) -> str:
    """Mask emails, phone numbers and card-like numbers (used before indexing / logging)."""
    if not text:
        return text
    text = _EMAIL.sub("[EMAIL]", text)
    text = _CARD.sub("[CARD]", text)
    text = _PHONE.sub("[PHONE]", text)
    return text


def rng(salt: str = "") -> random.Random:
    return random.Random(f"{SEED}:{salt}")


def stable_id(prefix: str, *parts: str) -> str:
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{h}"


def extract_skills(text: str) -> list[str]:
    low = str(text).lower() if text == text else ""
    found = []
    for s in ALL_SKILLS:
        pat = r"(?<![\w])" + re.escape(s) + r"(?![\w])" if len(s) <= 3 else re.escape(s)
        if re.search(pat, low):
            found.append(s)
    return found


def categorize(text: str) -> str:
    low = str(text).lower() if text == text else ""
    for cat, pat in CATEGORY_RULES:
        if re.search(pat, low):
            return cat
    return "other"


def persona_for_category(cat: str) -> str | None:
    return {"ai_ml": "ai_ml_engineer", "web_dev": "fullstack_web_dev",
            "data_analytics": "data_analyst"}.get(cat)


def write_jsonl(path: Path, rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
