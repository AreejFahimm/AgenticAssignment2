"""Config loader. Env var CONFIG_PATH overrides the file; MODEL_PROFILE overrides models.profile."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def load_config() -> dict:
    path = Path(os.getenv("CONFIG_PATH", ROOT / "agent" / "config.yaml"))
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    if os.getenv("MODEL_PROFILE"):
        cfg["models"]["profile"] = os.environ["MODEL_PROFILE"]
    return cfg


def reload_config() -> dict:
    load_config.cache_clear()
    return load_config()
