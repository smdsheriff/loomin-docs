#!/usr/bin/env bash
# =============================================================================
# Loomin-Docs Offline Package Builder (Sideload Script)
# =============================================================================
# Run this script on an internet-connected machine to prepare the complete
# offline package for deploying Loomin-Docs on an air-gapped RHEL 9 VM.
#
# Usage: bash sideload.sh [OUTPUT_DIR]
#   OUTPUT_DIR: path where the package will be created (default: ./package)
#
# Prerequisites on the build machine:
#   - Docker Engine with Compose plugin
#   - dnf/yumdownloader (for downloading RHEL 9 RPMs)
#   - Python 3.9+ with pip
#   - Ollama CLI (https://ollama.com)
#   - Sufficient disk space (~15-25 GB depending on model sizes)
#
# The output package/ directory can be transferred to the air-gapped VM
# via USB drive, SCP over a secure link, or any other transfer method.
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
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }
header()  { echo -e "\n${BOLD}${CYAN}=== $* ===${NC}\n"; }

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${1:-${SCRIPT_DIR}/package}"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"
OLLAMA_MODELS="llama3.2:1b gemma3:1b"
EMBEDDING_MODEL="all-MiniLM-L6-v2"
ARCHIVE_NAME="loomin-docs-package.tar.gz"

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
header "Pre-flight Checks"

MISSING_TOOLS=0

for tool in docker python3 pip3; do
    if command -v "${tool}" &>/dev/null; then
        success "${tool} found: $(${tool} --version 2>&1 | head -1)"
    else
        error "${tool} is not installed."
        MISSING_TOOLS=$((MISSING_TOOLS + 1))
    fi
done

# Check docker compose
if docker compose version &>/dev/null; then
    success "Docker Compose plugin found: $(docker compose version --short 2>/dev/null)"
else
    error "Docker Compose plugin not found."
    MISSING_TOOLS=$((MISSING_TOOLS + 1))
fi

# Check ollama
if command -v ollama &>/dev/null; then
    success "Ollama found: $(ollama --version 2>&1 | head -1)"
else
    error "Ollama CLI is not installed."
    error "Install from: https://ollama.com/download"
    MISSING_TOOLS=$((MISSING_TOOLS + 1))
fi

# Check for docker-compose.yml
if [[ -f "${COMPOSE_FILE}" ]]; then
    success "docker-compose.yml found at ${COMPOSE_FILE}"
else
    error "docker-compose.yml not found at ${COMPOSE_FILE}"
    MISSING_TOOLS=$((MISSING_TOOLS + 1))
fi

if [[ ${MISSING_TOOLS} -gt 0 ]]; then
    error "Missing ${MISSING_TOOLS} required tool(s). Install them and re-run."
    exit 1
fi

# ---------------------------------------------------------------------------
# 1. Create output directory structure
# ---------------------------------------------------------------------------
header "Creating Package Directory Structure"

DIRS=("rpms" "images" "models" "embedding-model")
for dir in "${DIRS[@]}"; do
    mkdir -p "${OUTPUT_DIR}/${dir}"
    success "Created ${OUTPUT_DIR}/${dir}/"
done

# ---------------------------------------------------------------------------
# 2. Download Docker RPMs for RHEL 9
# ---------------------------------------------------------------------------
header "Downloading Docker RPMs for RHEL 9"

info "Attempting to download Docker RPMs using dnf download..."
info "Target packages: docker-ce, docker-ce-cli, containerd.io, docker-compose-plugin"

# We need to download RPMs for RHEL 9 / CentOS Stream 9 / Rocky 9
# If running on a RHEL-family system, we can use dnf directly
# Otherwise, we use a Docker container to do the download

if command -v dnf &>/dev/null && [[ -f /etc/redhat-release ]]; then
    info "Detected RHEL-family system. Downloading RPMs natively..."

    # Add Docker repo if not present
    if [[ ! -f /etc/yum.repos.d/docker-ce.repo ]]; then
        info "Adding Docker CE repository..."
        dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo 2>/dev/null || \
        dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo 2>/dev/null || true
    fi

    # Use --resolve (not --alldeps) to avoid pulling system packages like systemd/grub
    # that conflict with the target RHEL 9 base install
    dnf download --resolve \
        --destdir="${OUTPUT_DIR}/rpms" \
        docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-buildx-plugin 2>&1 | \
        while IFS= read -r line; do echo "  ${line}"; done

else
    info "Not running on RHEL-family system. Using Docker container to download RPMs..."

    docker run --rm \
        -v "${OUTPUT_DIR}/rpms:/output" \
        rockylinux:9 \
        bash -c '
            dnf install -y dnf-plugins-core yum-utils 2>/dev/null
            dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
            dnf download --resolve \
                --destdir=/output \
                docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-buildx-plugin
        ' 2>&1 | while IFS= read -r line; do echo "  ${line}"; done
fi

RPM_COUNT=$(find "${OUTPUT_DIR}/rpms" -name "*.rpm" -type f | wc -l)
if [[ ${RPM_COUNT} -gt 0 ]]; then
    success "Downloaded ${RPM_COUNT} RPM package(s)."
else
    error "No RPMs were downloaded. Check network connectivity and repository access."
    exit 1
fi

# ---------------------------------------------------------------------------
# 3. Build and save Docker images
# ---------------------------------------------------------------------------
header "Building and Saving Docker Images"

# Build the application images
info "Building Loomin-Docs Docker images..."
docker compose -f "${COMPOSE_FILE}" build 2>&1 | while IFS= read -r line; do
    echo "  ${line}"
done
success "Docker images built."

# Image names must match docker-compose.yml image: fields exactly
FRONTEND_IMAGE="loomin-frontend:latest"
BACKEND_IMAGE="loomin-backend:latest"

# Save frontend image
info "Saving frontend image (${FRONTEND_IMAGE})..."
docker save "${FRONTEND_IMAGE}" -o "${OUTPUT_DIR}/images/frontend.tar"
FRONTEND_SIZE=$(du -h "${OUTPUT_DIR}/images/frontend.tar" | cut -f1)
success "Saved frontend image (${FRONTEND_SIZE})"

# Save backend image
info "Saving backend image (${BACKEND_IMAGE})..."
docker save "${BACKEND_IMAGE}" -o "${OUTPUT_DIR}/images/backend.tar"
BACKEND_SIZE=$(du -h "${OUTPUT_DIR}/images/backend.tar" | cut -f1)
success "Saved backend image (${BACKEND_SIZE})"

# Pull and save Ollama image
info "Pulling ollama/ollama:latest..."
docker pull ollama/ollama:latest 2>&1 | while IFS= read -r line; do
    echo "  ${line}"
done

info "Saving ollama image..."
docker save ollama/ollama:latest -o "${OUTPUT_DIR}/images/ollama.tar"
OLLAMA_SIZE=$(du -h "${OUTPUT_DIR}/images/ollama.tar" | cut -f1)
success "Saved ollama image (${OLLAMA_SIZE})"

# ---------------------------------------------------------------------------
# 4. Download Ollama model weights
# ---------------------------------------------------------------------------
header "Downloading Ollama Model Weights"

for model in ${OLLAMA_MODELS}; do
    info "Pulling ${model} model via Ollama..."
    ollama pull "${model}" 2>&1 | while IFS= read -r line; do
        echo "  ${line}"
    done
    success "Pulled ${model} model."
done

# Determine Ollama home directory
OLLAMA_HOME="${HOME}/.ollama/models"
# Try common locations
if [[ -d "${HOME}/.ollama/models" ]]; then
    OLLAMA_HOME="${HOME}/.ollama/models"
elif [[ -d "/usr/share/ollama/.ollama/models" ]]; then
    OLLAMA_HOME="/usr/share/ollama/.ollama/models"
fi

info "Copying Ollama model data from ${OLLAMA_HOME}..."

if [[ -d "${OLLAMA_HOME}" ]]; then
    cp -a "${OLLAMA_HOME}/." "${OUTPUT_DIR}/models/"
    MODEL_SIZE=$(du -sh "${OUTPUT_DIR}/models" | cut -f1)
    MODEL_FILES=$(find "${OUTPUT_DIR}/models" -type f | wc -l)
    success "Copied ${MODEL_FILES} model files (${MODEL_SIZE} total)."
else
    error "Ollama models directory not found at expected location."
    error "Tried: ${HOME}/.ollama/models and /usr/share/ollama/.ollama/models"
    error "Set OLLAMA_MODELS env var to the correct path and re-run."
    exit 1
fi

# ---------------------------------------------------------------------------
# 5. Download embedding model (sentence-transformers)
# ---------------------------------------------------------------------------
header "Downloading Embedding Model"

info "Installing sentence-transformers Python package (if needed)..."
pip3 install --quiet sentence-transformers 2>&1 | while IFS= read -r line; do
    echo "  ${line}"
done

info "Downloading and saving ${EMBEDDING_MODEL}..."
python3 -c "
from sentence_transformers import SentenceTransformer
import os

model_name = '${EMBEDDING_MODEL}'
output_path = os.path.join('${OUTPUT_DIR}', 'embedding-model', model_name)

print(f'  Downloading {model_name}...')
model = SentenceTransformer(model_name)

print(f'  Saving to {output_path}...')
model.save(output_path)

# Verify by listing saved files
file_count = sum(len(files) for _, _, files in os.walk(output_path))
print(f'  Saved {file_count} files.')
"

EMB_SIZE=$(du -sh "${OUTPUT_DIR}/embedding-model" | cut -f1)
success "Embedding model saved (${EMB_SIZE})."

# ---------------------------------------------------------------------------
# 6. Copy the deploy scripts into the package
# ---------------------------------------------------------------------------
header "Including Deployment Scripts"

info "Copying deployment files into package..."
# Use the production compose file (no build directives) for air-gapped deployment
cp "${SCRIPT_DIR}/docker-compose.prod.yml" "${OUTPUT_DIR}/docker-compose.yml"
cp "${SCRIPT_DIR}/setup.sh" "${OUTPUT_DIR}/"
cp "${SCRIPT_DIR}/ollama-entrypoint.sh" "${OUTPUT_DIR}/"
if [[ -f "${SCRIPT_DIR}/Makefile" ]]; then
    cp "${SCRIPT_DIR}/Makefile" "${OUTPUT_DIR}/"
fi

# Copy Modelfile as documentation artifact (system prompt is applied at API level)
MODELFILE="${PROJECT_ROOT}/backend/Modelfile"
if [[ -f "${MODELFILE}" ]]; then
    cp "${MODELFILE}" "${OUTPUT_DIR}/Modelfile"
    success "Modelfile copied (documentation artifact — system prompt applied via API)."
fi
success "Deployment scripts copied."

# ---------------------------------------------------------------------------
# 7. Create compressed archive
# ---------------------------------------------------------------------------
header "Creating Compressed Archive"

ARCHIVE_PATH="${SCRIPT_DIR}/${ARCHIVE_NAME}"

info "Compressing package to ${ARCHIVE_PATH} ..."
info "This may take several minutes depending on package size."

tar -czf "${ARCHIVE_PATH}" -C "$(dirname "${OUTPUT_DIR}")" "$(basename "${OUTPUT_DIR}")" 2>&1 | \
    while IFS= read -r line; do echo "  ${line}"; done

ARCHIVE_SIZE=$(du -h "${ARCHIVE_PATH}" | cut -f1)
success "Archive created: ${ARCHIVE_PATH} (${ARCHIVE_SIZE})"

# ---------------------------------------------------------------------------
# 8. Summary
# ---------------------------------------------------------------------------
header "Package Summary"

echo -e "${BOLD}Package contents:${NC}"
echo ""
du -sh "${OUTPUT_DIR}"/* 2>/dev/null | while IFS= read -r line; do
    echo "  ${line}"
done
echo ""
echo -e "${BOLD}Total package size:${NC}"
du -sh "${OUTPUT_DIR}" | while IFS= read -r line; do
    echo "  ${line}"
done
echo ""
echo -e "${BOLD}Compressed archive:${NC}"
echo "  ${ARCHIVE_PATH} (${ARCHIVE_SIZE})"
echo ""

echo -e "${GREEN}${BOLD}"
echo "  ╔══════════════════════════════════════════════════════════════╗"
echo "  ║                                                              ║"
echo "  ║   Offline package prepared successfully!                     ║"
echo "  ║                                                              ║"
echo "  ║   Next steps:                                                ║"
echo "  ║                                                              ║"
echo "  ║   1. Transfer to the air-gapped VM:                         ║"
echo "  ║      scp ${ARCHIVE_NAME} user@target:/tmp/          ║"
echo "  ║                                                              ║"
echo "  ║   2. On the target VM, extract:                              ║"
echo "  ║      tar -xzf ${ARCHIVE_NAME}                       ║"
echo "  ║                                                              ║"
echo "  ║   3. Run the bootstrap script:                               ║"
echo "  ║      sudo bash package/setup.sh package/                     ║"
echo "  ║                                                              ║"
echo "  ╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

info "Sideload preparation finished at $(date '+%Y-%m-%d %H:%M:%S')"
