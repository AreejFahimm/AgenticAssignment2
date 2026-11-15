"""Model access (open-first). Per-node model chosen in config.yaml; never in code.

profile 'offline' -> enabled(node) is False: nodes use their deterministic implementation (CI, demos, grading
without a GPU). Profiles 'open'/'paid' call any OpenAI-compatible endpoint (Ollama, vLLM, llama.cpp server, Groq,
OpenRouter, Together). Cheap nodes get a fallback model on failure (C7). Tokens and USD are tracked per node.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict

import httpx

from agent.config import ROOT, load_config

PROMPTS = ROOT / "agent" / "prompts"
USAGE: dict[str, dict] = defaultdict(lambda: dict(calls=0, tokens_in=0, tokens_out=0, usd=0.0, seconds=0.0))


def profile() -> str:
    return load_config()["models"]["profile"]


def _pcfg() -> dict:
    return load_config()["models"]["profiles"].get(profile(), {})


def enabled(node: str) -> bool:
    if profile() == "offline":
        return False
    p = _pcfg()
    return bool(os.getenv(p.get("base_url_env", ""), "")) and node in p.get("nodes", {})


def prompt(node: str) -> str:
    """Versioned prompt file for the node (R: no inline prompts)."""
    return (PROMPTS / f"{node}.md").read_text(encoding="utf-8")


def _call(model: str, system: str, user: str, json_mode: bool) -> tuple[str, int, int]:
    p = _pcfg()
    base = os.environ[p["base_url_env"]].rstrip("/")
    key = os.getenv(p.get("api_key_env", ""), "none")
    body = {"model": model, "temperature": 0.2,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    r = httpx.post(f"{base}/chat/completions", json=body, headers={"Authorization": f"Bearer {key}"}, timeout=120)
    r.raise_for_status()
    d = r.json()
    u = d.get("usage", {})
    return d["choices"][0]["message"]["content"], u.get("prompt_tokens", 0), u.get("completion_tokens", 0)


def complete(node: str, user: str, *, json_mode: bool = False) -> str:
    p = _pcfg()
    models = [p["nodes"][node]] + ([p["fallback"][node]] if node in p.get("fallback", {}) else [])
    last: Exception | None = None
    for m in models:
        t = time.time()
        try:
            text, tin, tout = _call(m, prompt(node), user, json_mode)
        except Exception as e:  # noqa: BLE001  fall through to fallback model
            last = e
            continue
        price = p.get("usd_per_mtok", {"in": 0, "out": 0})
        u = USAGE[node]
        u["calls"] += 1
        u["tokens_in"] += tin
        u["tokens_out"] += tout
        u["usd"] += (tin * price["in"] + tout * price["out"]) / 1e6
        u["seconds"] += time.time() - t
        return text
    raise RuntimeError(f"all models failed for node {node}: {last}")


def complete_json(node: str, user: str) -> dict:
    text = complete(node, user, json_mode=True)
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def usage_snapshot() -> dict:
    return {k: dict(v) for k, v in USAGE.items()}
