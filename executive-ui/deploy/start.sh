#!/bin/sh
# Container entrypoint: start the local model server, wait until it answers,
# then run the read-only API (which also serves the built React app). The
# model itself is already baked into the image (see Dockerfile) — this never
# downloads anything at runtime, so a Space waking from sleep starts in
# seconds, not minutes.
set -e

echo "Starting Ollama (model: ${BOTIM_LLM_MODEL})..."
ollama serve &

for i in $(seq 1 30); do
  if curl -fs "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
    echo "Ollama is ready."
    break
  fi
  sleep 1
done

echo "Starting the Opportunity Intelligence API on ${HOST}:${PORT}..."
exec python3 /app/executive-ui/api/server.py --root /app
