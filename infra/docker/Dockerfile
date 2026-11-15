# One image for api / worker / mcp servers / gigsim (command chosen by docker-compose). Multi-stage: build the web app, then Python.
FROM node:22-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
COPY agent agent
COPY apps/api apps/api
COPY apps/__init__.py apps/__init__.py
COPY rag rag
COPY mcp_servers mcp_servers
COPY worker worker
COPY gigsim_local gigsim_local
COPY evals evals
COPY scripts scripts
COPY data data
COPY --from=web /web/dist apps/web/dist
RUN pip install -e ".[worker,pdf]"
# Pre-download the open embedding + reranker models (CPU) so the first request is fast.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5'); from fastembed.rerank.cross_encoder import TextCrossEncoder; TextCrossEncoder('Xenova/ms-marco-MiniLM-L-6-v2')"
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
