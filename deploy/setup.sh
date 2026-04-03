#!/usr/bin/env bash
# =============================================================================
# Loomin-Docs Bootstrap Script for Air-Gapped RHEL 9
# =============================================================================
# This script installs Docker, loads container images, loads model weights,
# and starts the entire Loomin-Docs stack from a single USB/transfer directory.
#
# Usage: sudo bash setup.sh [PACKAGE_DIR]
#   PACKAGE_DIR: path to the directory containing all offline assets
#                (default: ./package)
#
# Expected package structure:
#   package/
#   ├── rpms/               # Docker RPMs for RHEL 9
#   │   ├── containerd.io-*.rpm
#   │   ├── docker-ce-*.rpm
#   │   ├── docker-ce-cli-*.rpm
#   │   ├── docker-compose-plugin-*.rpm
#   │   └── ... (dependencies)
#   ├── images/             # Docker images as .tar files
#   │   ├── frontend.tar
#   │   ├── backend.tar
#   │   └── ollama.tar
#   ├── models/             # Ollama model blobs
#   │   ├── blobs/
#   │   └── manifests/
#   └── embedding-model/    # Sentence-transformers model files
#       └── all-MiniLM-L6-v2/
#           ├── config.json
#           ├── tokenizer.json
#           ├── model.safetensors (or pytorch_model.bin)
#           └── ...
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Color output helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }
header()  { echo -e "\n${BOLD}${CYAN}=== $* ===${NC}\n"; }

# ---------------------------------------------------------------------------
# 1. Check root / sudo
# ---------------------------------------------------------------------------
header "Pre-flight Checks"

if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root (or with sudo)."
    echo "  Usage: sudo bash setup.sh [PACKAGE_DIR]"
    exit 1
fi
success "Running as root."

# ---------------------------------------------------------------------------
# 2. Resolve PACKAGE_DIR
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="${1:-${SCRIPT_DIR}/package}"
PACKAGE_DIR="$(cd "${PACKAGE_DIR}" 2>/dev/null && pwd || echo "${PACKAGE_DIR}")"

info "Package directory: ${PACKAGE_DIR}"

if [[ ! -d "${PACKAGE_DIR}" ]]; then
    error "Package directory not found: ${PACKAGE_DIR}"
    echo "  Provide the path as the first argument, or place assets in ./package/"
    exit 1
fi
success "Package directory exists."

# ---------------------------------------------------------------------------
# 3. Verify required files/directories
# ---------------------------------------------------------------------------
header "Verifying Package Contents"

REQUIRED_DIRS=("rpms" "images" "models" "embedding-model")
MISSING=0

for dir in "${REQUIRED_DIRS[@]}"; do
    if [[ -d "${PACKAGE_DIR}/${dir}" ]]; then
        FILE_COUNT=$(find "${PACKAGE_DIR}/${dir}" -type f | wc -l)
        success "${dir}/ found (${FILE_COUNT} files)"
    else
        error "${dir}/ is MISSING"
        MISSING=$((MISSING + 1))
    fi
done

if [[ ${MISSING} -gt 0 ]]; then
    error "${MISSING} required directory(ies) missing from package. Aborting."
    exit 1
fi

# Verify specific critical files
REQUIRED_IMAGES=("frontend.tar" "backend.tar" "ollama.tar")
for img in "${REQUIRED_IMAGES[@]}"; do
    if [[ -f "${PACKAGE_DIR}/images/${img}" ]]; then
        SIZE=$(du -h "${PACKAGE_DIR}/images/${img}" | cut -f1)
        success "images/${img} (${SIZE})"
    else
        error "images/${img} is MISSING"
        MISSING=$((MISSING + 1))
    fi
done

if [[ ${MISSING} -gt 0 ]]; then
    error "Required Docker image tar files are missing. Aborting."
    exit 1
fi

# Verify RPM files exist
RPM_COUNT=$(find "${PACKAGE_DIR}/rpms" -name "*.rpm" -type f | wc -l)
if [[ ${RPM_COUNT} -eq 0 ]]; then
    error "No .rpm files found in ${PACKAGE_DIR}/rpms/"
    exit 1
fi
success "Found ${RPM_COUNT} RPM package(s) in rpms/"

# Verify embedding model directory has content
if [[ ! -d "${PACKAGE_DIR}/embedding-model/all-MiniLM-L6-v2" ]]; then
    warn "embedding-model/all-MiniLM-L6-v2/ subdirectory not found."
    warn "Checking for model files directly in embedding-model/..."
    EMB_FILES=$(find "${PACKAGE_DIR}/embedding-model" -type f | wc -l)
    if [[ ${EMB_FILES} -eq 0 ]]; then
        error "No embedding model files found. Aborting."
        exit 1
    fi
    success "Found ${EMB_FILES} embedding model file(s)."
else
    success "Embedding model directory structure verified."
fi

success "All package contents verified."

# ---------------------------------------------------------------------------
# 4. Install Docker from local RPMs
# ---------------------------------------------------------------------------
header "Installing Docker Engine"

if command -v docker &>/dev/null; then
    DOCKER_VERSION=$(docker --version 2>/dev/null || echo "unknown")
    warn "Docker is already installed: ${DOCKER_VERSION}"
    info "Skipping RPM installation. Remove Docker first if you need a fresh install."
else
    info "Installing Docker RPMs from ${PACKAGE_DIR}/rpms/ ..."

    # Disable any external repos to prevent network access attempts
    # --allowerasing handles version conflicts with system packages (e.g., systemd)
    dnf install -y --disablerepo='*' --setopt=install_weak_deps=False --allowerasing \
        "${PACKAGE_DIR}"/rpms/*.rpm 2>&1 | while IFS= read -r line; do
        echo "  ${line}"
    done

    if ! command -v docker &>/dev/null; then
        error "Docker installation failed. Check RPM compatibility with this RHEL version."
        exit 1
    fi

    success "Docker RPMs installed successfully."
fi

# Enable and start Docker daemon
info "Enabling and starting Docker service..."
systemctl enable docker --now 2>/dev/null || true

# Wait for Docker daemon to be ready
RETRIES=0
MAX_RETRIES=30
while ! docker info &>/dev/null; do
    RETRIES=$((RETRIES + 1))
    if [[ ${RETRIES} -ge ${MAX_RETRIES} ]]; then
        error "Docker daemon failed to start within ${MAX_RETRIES} seconds."
        error "Check: systemctl status docker / journalctl -u docker"
        exit 1
    fi
    sleep 1
done
success "Docker daemon is running."

# Verify docker compose plugin is available
if docker compose version &>/dev/null; then
    COMPOSE_VERSION=$(docker compose version --short 2>/dev/null || echo "unknown")
    success "Docker Compose plugin available: v${COMPOSE_VERSION}"
else
    error "Docker Compose plugin is not available."
    error "Ensure docker-compose-plugin RPM is included in the rpms/ directory."
    exit 1
fi

# ---------------------------------------------------------------------------
# 5. Load Docker images from .tar files
# ---------------------------------------------------------------------------
header "Loading Docker Images"

for tarfile in "${PACKAGE_DIR}"/images/*.tar; do
    BASENAME=$(basename "${tarfile}")
    info "Loading ${BASENAME} ..."
    docker load -i "${tarfile}" 2>&1 | while IFS= read -r line; do
        echo "  ${line}"
    done
    success "Loaded ${BASENAME}"
done

info "Verifying loaded images..."
docker images --format "  {{.Repository}}:{{.Tag}} ({{.Size}})" | head -20
success "All Docker images loaded."

# ---------------------------------------------------------------------------
# 6. Create Docker volumes and populate with model data
# ---------------------------------------------------------------------------
header "Populating Docker Volumes"

# --- Embedding model volume ---
info "Creating and populating embedding-model volume..."

# Create the volume if it does not exist
docker volume create embedding-model &>/dev/null || true

# Determine the source path for the embedding model
EMB_SRC="${PACKAGE_DIR}/embedding-model"
if [[ -d "${PACKAGE_DIR}/embedding-model/all-MiniLM-L6-v2" ]]; then
    EMB_SRC="${PACKAGE_DIR}/embedding-model"
fi

# Use a temporary container to copy files into the volume
docker run --rm \
    -v embedding-model:/models \
    -v "${EMB_SRC}:/src:ro" \
    --entrypoint /bin/sh \
    ollama/ollama:latest \
    -c "cp -a /src/. /models/ && echo 'Embedding model files copied.'"

EMB_FILE_COUNT=$(docker run --rm -v embedding-model:/models --entrypoint /bin/sh \
    ollama/ollama:latest -c "find /models -type f | wc -l")
success "Embedding model volume populated (${EMB_FILE_COUNT} files)."

# --- Ollama model volume ---
info "Creating and populating ollama-data volume..."

docker volume create ollama-data &>/dev/null || true

# Copy model blobs and manifests into the Ollama data directory structure
docker run --rm \
    -v ollama-data:/root/.ollama \
    -v "${PACKAGE_DIR}/models:/src:ro" \
    --entrypoint /bin/sh \
    ollama/ollama:latest \
    -c "mkdir -p /root/.ollama/models && cp -a /src/. /root/.ollama/models/ && echo 'Ollama model files copied.'"

OLLAMA_FILE_COUNT=$(docker run --rm -v ollama-data:/root/.ollama --entrypoint /bin/sh \
    ollama/ollama:latest -c "find /root/.ollama -type f | wc -l")
success "Ollama data volume populated (${OLLAMA_FILE_COUNT} files)."

# --- Backend data volume ---
info "Creating backend-data volume..."
docker volume create backend-data &>/dev/null || true

# Pre-create the uploads and faiss_index directories inside the volume
docker run --rm \
    -v backend-data:/data \
    --entrypoint /bin/sh \
    ollama/ollama:latest \
    -c "mkdir -p /data/uploads /data/faiss_index && echo 'Backend data directories created.'"
success "Backend data volume initialized."

# ---------------------------------------------------------------------------
# 7. Start the stack
# ---------------------------------------------------------------------------
header "Starting Loomin-Docs Stack"

COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
    error "docker-compose.yml not found at ${COMPOSE_FILE}"
    error "Ensure this script is located alongside docker-compose.yml in the deploy/ directory."
    exit 1
fi

info "Starting services with docker compose..."
docker compose -f "${COMPOSE_FILE}" up -d 2>&1 | while IFS= read -r line; do
    echo "  ${line}"
done
success "Docker Compose services started."

# ---------------------------------------------------------------------------
# 8. Wait for services to become healthy
# ---------------------------------------------------------------------------
header "Waiting for Services"

wait_for_service() {
    local name="$1"
    local url="$2"
    local max_wait="$3"
    local elapsed=0

    info "Waiting for ${name} at ${url} (timeout: ${max_wait}s)..."
    while [[ ${elapsed} -lt ${max_wait} ]]; do
        if curl -sf -o /dev/null --max-time 3 "${url}" 2>/dev/null; then
            success "${name} is ready. (${elapsed}s)"
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
        # Print a dot every 10 seconds to show progress
        if (( elapsed % 10 == 0 )); then
            echo -ne "  ... ${elapsed}s elapsed\r"
        fi
    done
    error "${name} did not become ready within ${max_wait}s."
    return 1
}

# Ollama may take a while to load models into memory
wait_for_service "Ollama"   "http://localhost:11434/api/tags" 120 || {
    warn "Ollama is not responding. Check logs: docker compose -f ${COMPOSE_FILE} logs ollama"
}

wait_for_service "Backend"  "http://localhost:8000/docs" 60 || {
    warn "Backend is not responding. Check logs: docker compose -f ${COMPOSE_FILE} logs backend"
}

wait_for_service "Frontend" "http://localhost:80" 30 || {
    warn "Frontend is not responding. Check logs: docker compose -f ${COMPOSE_FILE} logs frontend"
}

# ---------------------------------------------------------------------------
# 9. Verify Ollama model availability
# ---------------------------------------------------------------------------
header "Verifying Ollama Model"

info "Checking if llama3 model is available in Ollama..."

# List models currently known to Ollama
MODELS_RESPONSE=$(curl -sf http://localhost:11434/api/tags 2>/dev/null || echo "{}")
if echo "${MODELS_RESPONSE}" | grep -qi "llama3"; then
    success "llama3 model is available in Ollama."
else
    warn "llama3 model not yet listed. Attempting to register it..."

    # If the blob files were copied correctly, Ollama should detect them.
    # Try creating the model from a Modelfile if available
    if [[ -f "${PACKAGE_DIR}/models/Modelfile" ]]; then
        info "Found Modelfile. Creating model via 'ollama create'..."
        docker compose -f "${COMPOSE_FILE}" exec -T ollama \
            ollama create llama3 -f /root/.ollama/models/Modelfile 2>&1 | while IFS= read -r line; do
            echo "  ${line}"
        done
    else
        # Attempt to trigger model detection by calling ollama list
        docker compose -f "${COMPOSE_FILE}" exec -T ollama ollama list 2>&1 | while IFS= read -r line; do
            echo "  ${line}"
        done
    fi

    # Re-check
    sleep 3
    MODELS_RESPONSE=$(curl -sf http://localhost:11434/api/tags 2>/dev/null || echo "{}")
    if echo "${MODELS_RESPONSE}" | grep -qi "llama3"; then
        success "llama3 model is now available."
    else
        warn "llama3 model may not be fully registered."
        warn "You may need to manually run: docker compose exec ollama ollama list"
        warn "Or copy the model manifest files into the correct Ollama directory."
    fi
fi

# ---------------------------------------------------------------------------
# 10. Print success message
# ---------------------------------------------------------------------------
header "Deployment Complete"

HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

echo -e "${GREEN}${BOLD}"
echo "  ╔══════════════════════════════════════════════════════════════╗"
echo "  ║                                                              ║"
echo "  ║   Loomin-Docs has been deployed successfully!                ║"
echo "  ║                                                              ║"
echo "  ║   Access the application:                                    ║"
echo "  ║     http://${HOST_IP}                                        ║"
echo "  ║     http://localhost                                         ║"
echo "  ║                                                              ║"
echo "  ║   API documentation:                                         ║"
echo "  ║     http://${HOST_IP}:8000/docs                              ║"
echo "  ║                                                              ║"
echo "  ║   Ollama API:                                                ║"
echo "  ║     http://${HOST_IP}:11434                                  ║"
echo "  ║                                                              ║"
echo "  ╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "${CYAN}Useful commands:${NC}"
echo "  View logs:       docker compose -f ${COMPOSE_FILE} logs -f"
echo "  Stop stack:      docker compose -f ${COMPOSE_FILE} down"
echo "  Restart stack:   docker compose -f ${COMPOSE_FILE} restart"
echo "  Check status:    docker compose -f ${COMPOSE_FILE} ps"
echo ""

info "Deployment finished at $(date '+%Y-%m-%d %H:%M:%S')"
