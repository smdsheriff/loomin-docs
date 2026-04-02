#!/bin/sh
# Do NOT use set -e — pull failures are expected in air-gapped mode

MODELS="${OLLAMA_MODELS:-llama3.2:1b gemma3:1b}"
READY_FILE="/tmp/.ollama-models-ready"

rm -f "$READY_FILE"

# Start ollama server in the background
ollama serve &
SERVER_PID=$!

# Wait for server to be ready
echo "[model-loader] Waiting for Ollama server..."
until ollama list >/dev/null 2>&1; do
  sleep 1
done
echo "[model-loader] Ollama server is ready."

# Give Ollama a moment to index pre-loaded model blobs from the volume
sleep 2
echo "[model-loader] Pre-loaded models detected:"
ollama list

# Pull or verify each model
for model in $MODELS; do
  BASE_NAME=$(echo "$model" | cut -d: -f1)
  if ollama list | grep -q "$BASE_NAME"; then
    echo "[model-loader] $model available (pre-loaded or cached)."
  else
    echo "[model-loader] $model not found. Attempting pull..."
    if ollama pull "$model" 2>&1; then
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

# Keep the server in the foreground
wait $SERVER_PID
