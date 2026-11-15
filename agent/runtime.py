"""Per-invocation runtime handed to nodes through config['configurable']['rt'] (not checkpointed)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from agent.config import load_config
from agent.mcp_client import MCPHub


@dataclass
class Runtime:
    hub: MCPHub = field(default_factory=MCPHub)
    cfg: dict = field(default_factory=load_config)
    seen: object | None = None  # SeenStore for scout dedup


def rt_of(config) -> Runtime:
    return config["configurable"]["rt"]


def tr(node: str, started: float, **kw) -> dict:
    """One execution-trace record (kept separate from decision state)."""
    return dict(node=node, ms=round((time.time() - started) * 1000), **kw)
