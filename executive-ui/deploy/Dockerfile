# BOTIM Opportunity Intelligence — single-container deploy (Render, or any
# Docker-capable host). Bundles the built React app + the read-only Python
# API in one lightweight image — no local model, no GPU, minimal RAM.
#
# AI analysis of new opportunities is delegated to a free, hosted,
# OpenAI-compatible LLM API (e.g. Groq — no card required) via
# BOTIM_LLM_BASE_URL / BOTIM_LLM_MODEL / BOTIM_LLM_API_KEY at runtime. Nothing
# is baked in at build time; if no provider is configured, the API honestly
# falls back to a deterministic offline scaffold.
#
# Build context is the REPOSITORY ROOT (see ../../README section "Deploy for
# free"), because the API needs the engines (opportunity-intelligence/,
# intelligence-monitoring/, impact/) and the committed knowledge-base/ data.

# ---- Stage 1: build the React app --------------------------------------- #
FROM node:20-slim AS frontend
WORKDIR /src
COPY executive-ui/web/package.json executive-ui/web/package-lock.json ./
RUN npm ci
COPY executive-ui/web/ ./
RUN npm run build

# ---- Stage 2: runtime (Python API only — stdlib, no dependencies) -------- #
FROM python:3.11-slim

ENV PORT=7860 \
    HOST=0.0.0.0 \
    HOME=/data
RUN mkdir -p /data && chmod -R 777 /data

WORKDIR /app
# Only what the API needs at runtime — the rest of the repo (tests, .git, the
# unbuilt web/ source) is not required to serve requests.
COPY opportunity-intelligence/tools/ /app/opportunity-intelligence/tools/
COPY intelligence-monitoring/tools/ /app/intelligence-monitoring/tools/
COPY impact/ /app/impact/
COPY knowledge-base/ /app/knowledge-base/
COPY executive-ui/adapter/ /app/executive-ui/adapter/
COPY executive-ui/api/ /app/executive-ui/api/
COPY --from=frontend /src/dist/ /app/executive-ui/web/dist/
# Render (and most container platforms) may run as a non-root, unpredictable
# UID — make everything the app touches world-writable so that's never a
# surprise.
RUN chmod -R 777 /app

EXPOSE 7860
CMD ["python3", "/app/executive-ui/api/server.py", "--root", "/app"]
