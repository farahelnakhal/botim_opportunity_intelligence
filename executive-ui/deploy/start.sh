#!/bin/sh
# Integration Phase 2 — single-container startup: run copilot-backend
# (loopback-only, never exposed directly) alongside executive-ui/api, which
# fronts both the built frontend and a reverse-proxy passthrough to
# copilot-backend at /copilot-api/*. See executive-ui/README.md,
# "Two backends, one container", for the full explanation.
set -e

COPILOT_HOST="${COPILOT_HOST:-127.0.0.1}"
COPILOT_PORT="${COPILOT_PORT:-8010}"

# Demo-safe default: if no live provider key is configured, run copilot-backend
# with the deterministic MockProvider rather than failing every chat request.
# MockProvider never fabricates — it only ever echoes the same grounded facts
# block a live model would also have received (see shared/llm/provider.py).
if [ -z "$ANTHROPIC_API_KEY" ] && [ -z "$COPILOT_PROVIDER" ]; then
  export COPILOT_PROVIDER=mock
  echo "start.sh: no ANTHROPIC_API_KEY set — running copilot-backend with COPILOT_PROVIDER=mock (deterministic, grounded-facts-only demo mode)"
fi

export COPILOT_HOST COPILOT_PORT
python3 /app/copilot-backend/server.py &
COPILOT_PID=$!
trap 'kill "$COPILOT_PID" 2>/dev/null || true' EXIT INT TERM

export COPILOT_UPSTREAM_URL="http://${COPILOT_HOST}:${COPILOT_PORT}"
exec python3 /app/executive-ui/api/server.py --root /app
