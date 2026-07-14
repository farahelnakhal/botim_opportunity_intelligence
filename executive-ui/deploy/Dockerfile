# BOTIM Opportunity Intelligence — single-container deploy (Render, or any
# Docker-capable host). Bundles the built React app + the read-only Python
# dashboard API + copilot-backend (Integration Phase 2) in one lightweight
# image — no local model, no GPU, minimal RAM.
#
# Two backends run in this one container (see executive-ui/deploy/start.sh):
#   - executive-ui/api/server.py — read-only dashboard API + static frontend
#     host + a fixed-destination reverse-proxy passthrough to copilot-backend
#     at /copilot-api/* (never an arbitrary/caller-supplied URL).
#   - copilot-backend/server.py  — the conversational, grounded copilot.
#     Binds 127.0.0.1 only; never reachable except through the proxy above.
#
# Grounded chat uses Anthropic Claude when ANTHROPIC_API_KEY is set; otherwise
# start.sh runs copilot-backend with the deterministic MockProvider (never
# fabricates — echoes only the same grounded facts a live model would also
# receive), so the demo is honest with no key configured at all. The legacy
# direct-LLM new-opportunity scaffold (executive-ui/api/generate.py) still
# supports BOTIM_LLM_BASE_URL / BOTIM_LLM_MODEL / BOTIM_LLM_API_KEY for that
# one narrowly-scoped compatibility endpoint (Phase 2J) — the normal chat UI
# no longer calls it.
#
# Build context is the REPOSITORY ROOT (see ../../README section "Deploy for
# free"), because both backends need the engines (opportunity-intelligence/,
# intelligence-monitoring/, impact/), shared/, merchant-voice/app/ (read-only
# Merchant Voice query layer), and the committed knowledge-base/ data.

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
# Only what the two backends need at runtime — the rest of the repo (tests,
# .git, the unbuilt web/ source, merchant-voice's server/tests) is not
# required to serve requests.
COPY opportunity-intelligence/tools/ /app/opportunity-intelligence/tools/
COPY intelligence-monitoring/tools/ /app/intelligence-monitoring/tools/
COPY impact/ /app/impact/
COPY knowledge-base/ /app/knowledge-base/
COPY executive-ui/adapter/ /app/executive-ui/adapter/
COPY executive-ui/api/ /app/executive-ui/api/
COPY executive-ui/deploy/start.sh /app/executive-ui/deploy/start.sh
COPY shared/ /app/shared/
COPY copilot-backend/app/ /app/copilot-backend/app/
COPY copilot-backend/server.py /app/copilot-backend/server.py
COPY merchant-voice/app/ /app/merchant-voice/app/
COPY --from=frontend /src/dist/ /app/executive-ui/web/dist/
# Render (and most container platforms) may run as a non-root, unpredictable
# UID — make everything the app touches world-writable so that's never a
# surprise.
RUN chmod -R 777 /app && chmod +x /app/executive-ui/deploy/start.sh

EXPOSE 7860
CMD ["/app/executive-ui/deploy/start.sh"]
