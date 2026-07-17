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

# Canonical LLM configuration is BOTIM_LLM_API_KEY / BOTIM_LLM_MODEL
# (+ BOTIM_LLM_BASE_URL / BOTIM_LLM_PROVIDER); ANTHROPIC_API_KEY /
# GROQ_API_KEY / COPILOT_* are optional aliases resolved by
# shared/llm/provider.py. The deterministic MOCK responder is only ever
# selected EXPLICITLY, or defaulted here in demo/test mode — a missing key in
# normal mode starts the copilot "unconfigured" (chat returns honest provider
# errors) rather than silently serving demo output.
HAS_LLM_KEY=""
if [ -n "${BOTIM_LLM_API_KEY:-}" ] || [ -n "${ANTHROPIC_API_KEY:-}" ] || [ -n "${GROQ_API_KEY:-}" ]; then
  HAS_LLM_KEY=1
fi
EXPLICIT_PROVIDER="${BOTIM_LLM_PROVIDER:-${COPILOT_PROVIDER:-}}"
if [ -z "$HAS_LLM_KEY" ] && [ -z "$EXPLICIT_PROVIDER" ]; then
  if [ "${BOTIM_APP_MODE:-normal}" = "demo" ] || [ "${BOTIM_APP_MODE:-normal}" = "test" ]; then
    export COPILOT_PROVIDER=mock
    echo "start.sh: ${BOTIM_APP_MODE} mode with no BOTIM_LLM_API_KEY — using the deterministic mock responder (grounded-facts-only demo output)"
  else
    echo "start.sh: ERROR =============================================================="
    echo "start.sh: ERROR  No LLM is configured (BOTIM_LLM_API_KEY is empty) and this"
    echo "start.sh: ERROR  is ${BOTIM_APP_MODE:-normal} mode. Chat will return honest provider"
    echo "start.sh: ERROR  errors until BOTIM_LLM_API_KEY (+ BOTIM_LLM_MODEL, and"
    echo "start.sh: ERROR  BOTIM_LLM_BASE_URL for non-Anthropic endpoints) is set."
    echo "start.sh: ERROR  Set BOTIM_LLM_PROVIDER=mock only for an explicit demo."
    echo "start.sh: ERROR =============================================================="
  fi
fi
if [ "${BOTIM_LLM_PROVIDER:-${COPILOT_PROVIDER:-}}" = "mock" ]; then
  RUNTIME_MODE="deterministic_demo"
elif [ -z "$HAS_LLM_KEY" ]; then
  RUNTIME_MODE="unconfigured"
else
  RUNTIME_MODE="live_model"
fi

# A NORMAL-mode deployment explicitly running on mock is still disclosed
# loudly (never silently) — the UI badge is the second disclosure layer.
if [ "${BOTIM_APP_MODE:-normal}" != "demo" ] && [ "$RUNTIME_MODE" = "deterministic_demo" ]; then
  echo "start.sh: WARNING ============================================================"
  echo "start.sh: WARNING  BOTIM_APP_MODE=${BOTIM_APP_MODE:-normal} but the chat provider is MOCK."
  echo "start.sh: WARNING  Production users would see deterministic demo output, not"
  echo "start.sh: WARNING  live model synthesis. Set BOTIM_LLM_API_KEY (and remove the"
  echo "start.sh: WARNING  explicit mock provider setting) for real use."
  echo "start.sh: WARNING ============================================================"
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

log "starting copilot-backend on ${COPILOT_HOST}:${COPILOT_PORT} (provider=${BOTIM_LLM_PROVIDER:-${COPILOT_PROVIDER:-auto}}, runtime_mode=${RUNTIME_MODE})"
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
