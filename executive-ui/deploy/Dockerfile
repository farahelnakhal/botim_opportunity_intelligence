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
# PR1 (production cleanup) — the image defaults to the clean NORMAL mode.
# The public demo showcase is an explicit opt-in:
#   docker build --build-arg APP_MODE=demo -f executive-ui/deploy/Dockerfile .
# A real product deployment builds with no args and gets: no demo corpus, no
# demo persona/recipients, no demo seed fallback, honest empty first-run
# workspace. (BOTIM_APP_MODE can still be overridden at runtime; the backend
# resolves any invalid value to normal — never silently to demo.)
ARG APP_MODE=normal

FROM node:20-slim AS frontend
ARG APP_MODE
WORKDIR /src
COPY executive-ui/web/package.json executive-ui/web/package-lock.json ./
RUN npm ci
COPY executive-ui/web/ ./
# Build-time hint: ONLY a demo build may use the bundled demo seed as the
# offline fallback; normal builds never fall back to demo data.
ENV VITE_APP_MODE=$APP_MODE
RUN npm run build

# ---- Stage 2: runtime (Python API only — stdlib, no dependencies) -------- #
FROM python:3.11-slim
ARG APP_MODE

# PR1 — the runtime mode follows the build's APP_MODE (default: normal, the
# clean production workspace). Demo showcase deployments build with
# --build-arg APP_MODE=demo. Phase 6 — the runtime user-opportunity DB lives
# on the writable volume, never inside the image's committed knowledge base.
ENV PORT=7860 \
    HOST=0.0.0.0 \
    HOME=/data \
    BOTIM_APP_MODE=$APP_MODE \
    USER_OPPORTUNITIES_DB_PATH=/data/runtime/user-opportunities.db \
    RESEARCH_DB_PATH=/data/runtime/research.db
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
