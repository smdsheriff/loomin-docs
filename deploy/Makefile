# =============================================================================
# Loomin-Docs Deployment Makefile
# =============================================================================
# Convenience targets for building, running, and managing the Loomin-Docs stack.
#
# Usage:
#   make build            Build all Docker images
#   make up               Start the stack in detached mode
#   make down             Stop and remove all containers
#   make logs             Tail logs from all services
#   make ps               Show running containers
#   make restart          Restart all services
#   make prepare-offline  Build the offline deployment package (requires internet)
#   make deploy-offline   Run the air-gapped bootstrap script (requires root)
# =============================================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Paths
COMPOSE_FILE := $(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))/docker-compose.yml
SCRIPT_DIR := $(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))
COMPOSE := docker compose -f $(COMPOSE_FILE)

# Colors for help target
CYAN := \033[0;36m
NC := \033[0m

# =============================================================================
# Development Targets
# =============================================================================

.PHONY: build
build: ## Build all Docker images
	$(COMPOSE) build

.PHONY: up
up: ## Start the stack in detached mode
	$(COMPOSE) up -d

.PHONY: down
down: ## Stop and remove all containers
	$(COMPOSE) down

.PHONY: logs
logs: ## Tail logs from all services (Ctrl+C to stop)
	$(COMPOSE) logs -f

.PHONY: logs-backend
logs-backend: ## Tail logs from the backend service only
	$(COMPOSE) logs -f backend

.PHONY: logs-frontend
logs-frontend: ## Tail logs from the frontend service only
	$(COMPOSE) logs -f frontend

.PHONY: logs-ollama
logs-ollama: ## Tail logs from the Ollama service only
	$(COMPOSE) logs -f ollama

.PHONY: ps
ps: ## Show status of running containers
	$(COMPOSE) ps

.PHONY: restart
restart: ## Restart all services
	$(COMPOSE) restart

.PHONY: restart-backend
restart-backend: ## Restart only the backend service
	$(COMPOSE) restart backend

.PHONY: stop
stop: ## Stop all services without removing containers
	$(COMPOSE) stop

.PHONY: pull
pull: ## Pull latest base images
	$(COMPOSE) pull

# =============================================================================
# Offline Deployment Targets
# =============================================================================

.PHONY: prepare-offline
prepare-offline: ## Build the offline deployment package (requires internet)
	@echo "=== Preparing offline deployment package ==="
	bash $(SCRIPT_DIR)/sideload.sh $(SCRIPT_DIR)/package

.PHONY: deploy-offline
deploy-offline: ## Run the air-gapped bootstrap script (requires root)
	@if [ "$$(id -u)" -ne 0 ]; then \
		echo "ERROR: deploy-offline must be run as root (use sudo make deploy-offline)"; \
		exit 1; \
	fi
	bash $(SCRIPT_DIR)/setup.sh $(SCRIPT_DIR)/package

# =============================================================================
# Maintenance Targets
# =============================================================================

.PHONY: clean
clean: down ## Stop stack and remove volumes (WARNING: destroys data)
	$(COMPOSE) down -v
	@echo "All containers and volumes removed."

.PHONY: shell-backend
shell-backend: ## Open a shell in the backend container
	$(COMPOSE) exec backend /bin/bash

.PHONY: shell-ollama
shell-ollama: ## Open a shell in the Ollama container
	$(COMPOSE) exec ollama /bin/bash

.PHONY: ollama-models
ollama-models: ## List models available in Ollama
	$(COMPOSE) exec ollama ollama list

.PHONY: test-rag
test-rag: ## Run the RAG faithfulness verification test
	python3 $(SCRIPT_DIR)/../tests/verify_rag.py --api-url http://localhost:8000

.PHONY: health
health: ## Check health of all services
	@echo "--- Frontend (port 80) ---"
	@curl -sf -o /dev/null -w "HTTP %{http_code}\n" http://localhost:80 || echo "UNREACHABLE"
	@echo "--- Backend (port 8000) ---"
	@curl -sf -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8000/docs || echo "UNREACHABLE"
	@echo "--- Ollama (port 11434) ---"
	@curl -sf -o /dev/null -w "HTTP %{http_code}\n" http://localhost:11434/api/tags || echo "UNREACHABLE"

# =============================================================================
# Help
# =============================================================================

.PHONY: help
help: ## Show this help message
	@echo ""
	@echo "Loomin-Docs Deployment"
	@echo "====================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
