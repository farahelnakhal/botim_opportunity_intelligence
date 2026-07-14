# BOTIM Opportunity Intelligence — single-container deploy for Hugging Face
# Spaces (free CPU tier, no GPU/credit card required).
#
# Bundles: the built React app, the read-only Python API, and a local Ollama
# model — one process, one public URL, no external services or paid API keys.
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

# ---- Stage 2: runtime (Python API + Ollama) ------------------------------ #
FROM python:3.11-slim

# Ollama's official installer (no package-manager dependency, works on slim).
# curl is kept (not purged) — start.sh uses it for the readiness check.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && curl -fsSL https://ollama.com/install.sh | sh \
 && rm -rf /var/lib/apt/lists/*

# Free Hugging Face Spaces have NO persistent disk by default — anything
# written at container start is re-downloaded on every sleep/wake. So the
# model is pulled once HERE, at build time, and baked into the image; waking
# from sleep only restarts a container (seconds), never re-downloads weights.
ARG OLLAMA_MODEL=llama3.2:1b
ENV OLLAMA_MODELS=/opt/ollama-models \
    OLLAMA_HOST=127.0.0.1:11434 \
    BOTIM_LLM_BASE_URL=http://127.0.0.1:11434/v1 \
    BOTIM_LLM_MODEL=${OLLAMA_MODEL} \
    PORT=7860 \
    HOST=0.0.0.0
RUN mkdir -p "$OLLAMA_MODELS"; \
    ollama serve & \
    OLLAMA_PID=$!; \
    for i in $(seq 1 30); do curl -fs http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break; sleep 1; done && \
    ollama pull "$OLLAMA_MODEL" && \
    kill "$OLLAMA_PID" && \
    chmod -R 777 "$OLLAMA_MODELS"

# Hugging Face Spaces may run the container as a non-root, unpredictable UID —
# make everything the app touches world-writable so that's never a surprise.
ENV HOME=/data
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
COPY executive-ui/deploy/start.sh /app/start.sh
RUN chmod +x /app/start.sh && chmod -R 777 /app

EXPOSE 7860
ENTRYPOINT ["/app/start.sh"]
