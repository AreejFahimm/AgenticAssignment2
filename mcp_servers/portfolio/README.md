# GigBid Portfolio MCP server

Read-only MCP server that lets any MCP host (Claude Desktop, Cursor, GigBid's agents) search a freelancer's portfolio for **evidence**
(case studies, repo READMEs, code, reviews) and load full items. Built with the official MCP Python SDK (FastMCP).

| | |
|---|---|
| Tools | `search_evidence(requirement, k, filters)` · `get_case_study(id)` · `list_skills()` |
| Resources | `portfolio://case/{id}` · `portfolio://proposal/{id}` |
| Prompts | *Answer a screening question from my portfolio* · *Write a proposal opening grounded in my work* · *Find gaps between a job post and my portfolio* |
| Safety | read-only (all tools annotated `readOnlyHint`), `k` bounded 1–20, path traversal blocked, no network access |

## Run
```bash
pip install -e .                                   # from the GigBid repo root
PORTFOLIO_PERSONA=ai_ml_engineer python -m mcp_servers.portfolio.server          # stdio
python -m mcp_servers.portfolio.server --http --port 9101                         # Streamable HTTP
```
### Claude Desktop / Cursor
```json
{ "mcpServers": { "gigbid-portfolio": { "command": "python", "args": ["-m", "mcp_servers.portfolio.server"],
  "env": { "PORTFOLIO_PERSONA": "ai_ml_engineer" } } } }
```
### Docker (documented install command)
```bash
docker build -f infra/docker/Dockerfile -t gigbid-portfolio .
docker run -i --rm -e PORTFOLIO_PERSONA=data_analyst gigbid-portfolio python -m mcp_servers.portfolio.server
```
### uvx from GitHub (after you push the repo)
```bash
uvx --from git+https://github.com/<you>/<repo> python -m mcp_servers.portfolio.server
```
> **To publish (your step):** push the repo, push the image to GHCR/Docker Hub or publish to PyPI, then replace `<you>/<repo>` above and put the link in the Classroom submission.

## Using your own portfolio
Drop Markdown case studies into `data/personas/<your_id>/case_studies/`, build `evidence.jsonl` (see `scripts/gen_personas.py` for the schema) or upload files in the GigBid UI (incremental re-indexing).
The retrieval design behind `search_evidence` is selected in `agent/config.yaml` (`rag.variant`) by evaluation; see the main README.
The corpora shipped here are **synthetic**.
