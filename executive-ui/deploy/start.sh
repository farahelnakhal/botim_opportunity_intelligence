#!/usr/bin/env bash
# Integration Phase 3 — single-container startup, rewritten for real process
# lifecycle management: run copilot-backend (loopback-only, never exposed
# directly) alongside executive-ui/api, which fronts both the built frontend
# and a reverse-proxy passthrough to copilot-backend at /copilot-api/*. See
# executive-ui/README.md, "Two backends, one container", for the full
# explanation.
#
# This script stays the parent of both child processes for its entire life
# (no `exec` handoff to either one) so it can:
#   - start copilot-backend first and wait for it to actually be ready
#     before starting executive-ui/api at all;
#   - forward INT/TERM to both children and reap them on any exit path;
#   - stop the other service the moment either child exits unexpectedly;
#   - return a non-zero exit code whenever the required copilot-backend
#     readiness check does not succeed, instead of silently proceeding.
# It never logs secrets, tokens, prompts, or request/response payloads —
# only service name, host, port, runtime mode, and readiness outcome.
set -u

COPILOT_HOST="${COPILOT_HOST:-127.0.0.1}"
COPILOT_PORT="${COPILOT_PORT:-8010}"
# EXECUTIVE_API_HOST/PORT fall back to the PORT/HOST convention most
# container platforms already set (see the Dockerfile), so existing deploys
# keep working unchanged.
EXECUTIVE_API_HOST="${EXECUTIVE_API_HOST:-${HOST:-0.0.0.0}}"
EXECUTIVE_API_PORT="${EXECUTIVE_API_PORT:-${PORT:-7860}}"
COPILOT_READINESS_TIMEOUT_SECONDS="${COPILOT_READINESS_TIMEOUT_SECONDS:-20}"
COPILOT_READINESS_INTERVAL_SECONDS="${COPILOT_READINESS_INTERVAL_SECONDS:-0.5}"
# Entrypoints are overridable so lifecycle tests can substitute stub scripts
# for the two real servers without touching this script.
COPILOT_ENTRYPOINT="${COPILOT_ENTRYPOINT:-/app/copilot-backend/server.py}"
EXECUTIVE_API_ENTRYPOINT="${EXECUTIVE_API_ENTRYPOINT:-/app/executive-ui/api/server.py}"

# Demo-safe default: if no live provider key is configured, run copilot-backend
# with the deterministic MockProvider rather than failing every chat request.
# MockProvider never fabricates — it only ever echoes the same grounded facts
# block a live model would also have received (see shared/llm/provider.py).
if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${COPILOT_PROVIDER:-}" ]; then
  export COPILOT_PROVIDER=mock
  echo "start.sh: no ANTHROPIC_API_KEY set — running copilot-backend with COPILOT_PROVIDER=mock (deterministic, grounded-facts-only demo mode)"
fi
if [ "${COPILOT_PROVIDER:-anthropic}" = "mock" ]; then
  RUNTIME_MODE="deterministic_demo"
else
  RUNTIME_MODE="live_model"
fi

export COPILOT_HOST COPILOT_PORT

log() {
  # Safe, structured status lines only.
  echo "start.sh: $*"
}

COPILOT_PID=""
EXEC_PID=""

term_children() {
  # Idempotent — safe to call more than once (e.g. from both an explicit
  # failure path and the EXIT safety-net trap).
  if [ -n "$EXEC_PID" ] && kill -0 "$EXEC_PID" 2>/dev/null; then
    log "stopping executive-ui/api (pid $EXEC_PID)"
    kill -TERM "$EXEC_PID" 2>/dev/null || true
  fi
  if [ -n "$COPILOT_PID" ] && kill -0 "$COPILOT_PID" 2>/dev/null; then
    log "stopping copilot-backend (pid $COPILOT_PID)"
    kill -TERM "$COPILOT_PID" 2>/dev/null || true
  fi
  [ -n "$EXEC_PID" ] && wait "$EXEC_PID" 2>/dev/null
  [ -n "$COPILOT_PID" ] && wait "$COPILOT_PID" 2>/dev/null
}

fail() {
  log "$1"
  trap '' INT TERM EXIT
  term_children
  exit 1
}

on_signal() {
  trap '' INT TERM EXIT
  log "received $1 — shutting down"
  term_children
  exit 0
}
trap 'on_signal INT' INT
trap 'on_signal TERM' TERM
trap term_children EXIT   # safety net so no child ever survives this process

log "starting copilot-backend on ${COPILOT_HOST}:${COPILOT_PORT} (provider=${COPILOT_PROVIDER:-anthropic}, runtime_mode=${RUNTIME_MODE})"
python3 "$COPILOT_ENTRYPOINT" &
COPILOT_PID=$!

# ---- readiness: bounded TCP-connect poll --------------------------------- #
# curl is not guaranteed to be present in the runtime image, so the probe is
# plain Python stdlib. A successful connect proves the HTTP server is bound
# and accepting connections — copilot-backend only binds once fully
# initialized, so this is a genuine readiness signal, not a fixed sleep.
python3 - "$COPILOT_HOST" "$COPILOT_PORT" \
  "$COPILOT_READINESS_TIMEOUT_SECONDS" "$COPILOT_READINESS_INTERVAL_SECONDS" <<'PY'
import socket
import sys
import time

host, port = sys.argv[1], int(sys.argv[2])
timeout_s, interval_s = float(sys.argv[3]), float(sys.argv[4])
deadline = time.time() + timeout_s
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=interval_s):
            sys.exit(0)
    except OSError:
        time.sleep(interval_s)
sys.exit(1)
PY
READY=$?

if ! kill -0 "$COPILOT_PID" 2>/dev/null; then
  fail "copilot-backend exited before becoming ready — aborting startup"
fi
if [ "$READY" -ne 0 ]; then
  fail "copilot-backend did not become ready within ${COPILOT_READINESS_TIMEOUT_SECONDS}s — aborting startup"
fi
log "copilot-backend is ready"

export COPILOT_UPSTREAM_URL="http://${COPILOT_HOST}:${COPILOT_PORT}"
log "starting executive-ui/api on ${EXECUTIVE_API_HOST}:${EXECUTIVE_API_PORT}"
python3 "$EXECUTIVE_API_ENTRYPOINT" --root /app \
  --host "$EXECUTIVE_API_HOST" --port "$EXECUTIVE_API_PORT" &
EXEC_PID=$!

# ---- supervise: if either child exits unexpectedly, stop the other ------- #
while true; do
  wait -n "$COPILOT_PID" "$EXEC_PID"
  if ! kill -0 "$COPILOT_PID" 2>/dev/null; then
    wait "$COPILOT_PID"; code=$?
    fail "copilot-backend exited unexpectedly (exit ${code}) — stopping executive-ui/api"
  fi
  if ! kill -0 "$EXEC_PID" 2>/dev/null; then
    wait "$EXEC_PID"; code=$?
    fail "executive-ui/api exited unexpectedly (exit ${code}) — stopping copilot-backend"
  fi
done
