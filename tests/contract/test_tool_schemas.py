"""Schema snapshot test (A7): fails CI when any MCP tool signature changes unintentionally.

Intentional change?  UPDATE_SNAPSHOTS=1 pytest tests/contract  and commit the new snapshot.
"""
import json
import os
import sys
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session as connect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
SNAP = Path(__file__).parent / "snapshots" / "tools.json"

from mcp_servers.marketplace import server as market  # noqa: E402
from mcp_servers.portfolio import server as portfolio  # noqa: E402
from mcp_servers.workspace import server as workspace  # noqa: E402


async def _dump() -> dict:
    out = {}
    for name, srv in (("portfolio", portfolio.mcp), ("marketplace", market.mcp), ("workspace", workspace.mcp)):
        async with connect(srv._mcp_server) as c:
            for t in (await c.list_tools()).tools:
                out[f"{name}.{t.name}"] = dict(
                    inputSchema=t.inputSchema, outputSchema=t.outputSchema,
                    annotations=t.annotations.model_dump(exclude_none=True) if t.annotations else None)
    return json.loads(json.dumps(out, sort_keys=True))


async def test_tool_signatures_match_snapshot():
    current = await _dump()
    if os.getenv("UPDATE_SNAPSHOTS") or not SNAP.exists():
        SNAP.parent.mkdir(exist_ok=True)
        SNAP.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
    saved = json.loads(SNAP.read_text(encoding="utf-8"))
    assert current == saved, "MCP tool signature changed; rerun with UPDATE_SNAPSHOTS=1 if intentional"


async def test_every_tool_has_annotations_and_output_schema():
    for key, spec in (await _dump()).items():
        assert spec["annotations"] and "readOnlyHint" in spec["annotations"], key
        assert spec["outputSchema"], key
