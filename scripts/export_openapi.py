"""Export FastAPI's OpenAPI schema -> apps/web/openapi.json (then `npm run gen:api` generates the typed TS client)."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("APP_DB", ":memory:")
os.environ.setdefault("MEMORY_DB", ":memory:")

from apps.api.main import app  # noqa: E402

out = Path(__file__).resolve().parents[1] / "apps" / "web" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
print("wrote", out, "paths:", len(app.openapi()["paths"]))
