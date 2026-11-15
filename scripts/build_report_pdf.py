"""docs/REPORT.md -> docs/REPORT.html -> docs/REPORT.pdf (local headless Chromium via Playwright; nothing is uploaded)."""
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evals.runners.results_table import render  # noqa: E402

md = (ROOT / "docs" / "REPORT.md").read_text(encoding="utf-8") + chr(10) * 2 + render()
body = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])
css = """body{font:10.5px/1.35 'Segoe UI',Arial,sans-serif;margin:0;color:#111}h1{font-size:19px;margin:0 0 4px}h2{font-size:13.5px;margin:12px 0 4px;border-bottom:1px solid #ccc}
h3{font-size:11.5px;margin:8px 0 3px}table{border-collapse:collapse;width:100%;margin:4px 0}th,td{border:1px solid #bbb;padding:2px 5px;text-align:left;vertical-align:top}
th{background:#eee}code{font-size:9.5px;background:#f3f3f3;padding:0 2px}p,li{margin:2px 0}ul,ol{margin:2px 0 2px 16px;padding:0}"""
html = f"<!doctype html><meta charset='utf-8'><style>{css}</style>{body}"
(ROOT / "docs" / "REPORT.html").write_text(html, encoding="utf-8")
js = ROOT / "apps" / "web" / "md2pdf.mjs"
js.write_text("""import { chromium } from "@playwright/test";
import { pathToFileURL } from "node:url";
const [,, src, out] = process.argv;
const b = await chromium.launch(); const p = await b.newPage();
await p.goto(pathToFileURL(src).href);
await p.pdf({ path: out, format: "A4", margin: { top: "14mm", bottom: "14mm", left: "13mm", right: "13mm" }, printBackground: true });
await b.close();
""", encoding="utf-8")
r = subprocess.run(["node", str(js), str(ROOT / "docs" / "REPORT.html"), str(ROOT / "docs" / "REPORT.pdf")], cwd=ROOT / "apps" / "web")
sys.exit(r.returncode)
