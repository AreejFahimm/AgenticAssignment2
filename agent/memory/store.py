"""Long-term memory on a LangGraph store (C2). Two stores, both written ONLY via promotion_rules:

  style    ("style", user_id)        learned from the user's edits to drafts ("cut the first sentence", "never say passionate")
  outcome  ("outcome", user_id, cat) what won / got replies per job category

Raw tool output is never written here. Candidate observations are kept in ("style_events", user_id) and are
promoted into ("style", user_id) only when the rule in promotion_rules.py is met. The UI memory viewer lists and
deletes items from these namespaces (Settings screen).
"""
from __future__ import annotations

import os
import sqlite3
from functools import lru_cache
from pathlib import Path

from langgraph.store.memory import InMemoryStore
from langgraph.store.sqlite import SqliteStore

from agent.config import ROOT


@lru_cache(maxsize=1)
def get_store():
    path = os.getenv("MEMORY_DB")
    if path == ":memory:":
        return InMemoryStore()
    p = Path(path) if path else ROOT / "data" / "processed" / "memory.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    store = SqliteStore(sqlite3.connect(str(p), check_same_thread=False, isolation_level=None))
    store.setup()
    return store


def reset_store_cache() -> None:
    get_store.cache_clear()


def list_memory(user_id: str) -> list[dict]:
    """Everything the user can see/delete in the memory viewer."""
    out = []
    for ns in (("style", user_id), ("style_events", user_id), ("outcome", user_id)):
        for item in get_store().search(ns, limit=200):
            out.append(dict(namespace="/".join(item.namespace), key=item.key, value=item.value))
    return out


def delete_memory(user_id: str, namespace: str, key: str) -> None:
    ns = tuple(namespace.split("/"))
    if ns[1] != user_id:  # tenant scoping: a user can only delete their own memory
        raise PermissionError("not your memory")
    get_store().delete(ns, key)
