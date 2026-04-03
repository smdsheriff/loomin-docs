#!/bin/sh
# Do NOT use set -e — pull failures are expected in air-gapped mode

MODELS="${OLLAMA_MODELS:-llama3.2:1b gemma3:1b}"
READY_FILE="/tmp/.ollama-models-ready"

rm -f "$READY_FILE"

# Start ollama server in the background
ollama serve &
SERVER_PID=$!

# Forward SIGTERM to ollama for graceful shutdown
trap 'kill $SERVER_PID; wait $SERVER_PID; exit $?' TERM INT

# Wait for server to be ready (with timeout)
echo "[model-loader] Waiting for Ollama server..."
ELAPSED=0
TIMEOUT=60
until ollama list >/dev/null 2>&1; do
  sleep 1
  ELAPSED=$((ELAPSED + 1))
  if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
    echo "[model-loader] ERROR: Ollama server failed to start within ${TIMEOUT}s"
    exit 1
  fi
done
echo "[model-loader] Ollama server is ready. (${ELAPSED}s)"

# Give Ollama a moment to index pre-loaded model blobs from the volume
sleep 2
echo "[model-loader] Pre-loaded models detected:"
ollama list

# Pull or verify each model
for model in $MODELS; do
  # Check exact model name match (not substring)
  if ollama list | awk '{print $1}' | grep -qx "$model"; then
    echo "[model-loader] $model available (pre-loaded or cached)."
  else
    echo "[model-loader] $model not found. Attempting pull (10s timeout)..."
    if timeout 10 ollama pull "$model" 2>&1; then
      echo "[model-loader] $model pulled successfully."
    else
      echo "[model-loader] WARNING: Could not pull $model (expected in air-gapped mode)."
    fi
  fi
done

# NOTE: The Modelfile (backend/Modelfile) documents the system prompt and
# parameters used for the RAG assistant.  The system prompt is applied at the
# API level in chat.py for ALL models, so we do NOT create a separate "loomin"
# model here — that would duplicate the prompt for users who select it.

echo ""
echo "[model-loader] Final model inventory:"
ollama list

# Mark as ready
MODEL_COUNT=$(ollama list | tail -n +2 | wc -l)
touch "$READY_FILE"
echo "[model-loader] $MODEL_COUNT model(s) available. Readiness marker created."

# Keep the server in the foreground and propagate its exit code
wait $SERVER_PID
exit $?
