.PHONY: all run dev start stop install test clean help docker-build docker-up docker-down docker-logs qwen-server qwen-download qwen-stop

PYTHON ?= python3
PORT ?= 8080

help:
	@echo "Swarm AI Studio Commands:"
	@echo "  make run            - Run web server in foreground (default)"
	@echo "  make qwen-server    - Launch Qwen 3.8 27B continuous batching server (3 slots)"
	@echo "  make qwen-download  - Download Qwen 3.8 27B Q4_K_S GGUF model"
	@echo "  make qwen-stop      - Stop running local Qwen GPU server"
	@echo "  make dev            - Run server in interactive development mode"
	@echo "  make start          - Launch server in background daemon mode"
	@echo "  make stop           - Stop background server daemon"
	@echo "  make install        - Install Python package and dependencies"
	@echo "  make test           - Run full unit test suite"
	@echo "  make clean          - Clean cache and temporary build artifacts"
	@echo "  make docker-build - Build the Docker image"
	@echo "  make docker-up    - Build & run via docker compose (detached)"
	@echo "  make docker-down  - Stop and remove the docker compose stack"
	@echo "  make docker-logs  - Tail container logs"

all: run

install:
	@echo "Installing dependencies..."
	$(PYTHON) -m pip install -r requirements.txt
	chmod +x bin/swarm bin/qwen_oracle.sh scripts/*.sh

run:
	@$(PYTHON) bin/swarm web --port $(PORT)

qwen-server:
	@./bin/launch_qwen38_27b.sh

qwen-download:
	@$(PYTHON) scripts/download_qwen38_27b.py

qwen-stop:
	@fuser -k 8034/tcp 2>/dev/null || true
	@echo "✓ Qwen 3.8 27B server stopped."

dev:
	@./scripts/dev.sh

start:
	@./scripts/start.sh

stop:
	@./scripts/stop.sh

test:
	@echo "Running unit test suite..."
	$(PYTHON) -m unittest discover -s tests -v

clean:
	@rm -rf build/ dist/ *.egg-info __pycache__ */__pycache__ */*/__pycache__ .pytest_cache
	@echo "✓ Clean complete."

DOCKER_COMPOSE := $(shell command -v docker-compose 2>/dev/null || echo "docker compose")

docker-build:
	$(DOCKER_COMPOSE) build

docker-up:
	$(DOCKER_COMPOSE) up -d --build
	@echo "✓ Swarm AI Studio running at http://localhost:$${SWARM_PORT:-8080}"

docker-down:
	$(DOCKER_COMPOSE) down

docker-logs:
	$(DOCKER_COMPOSE) logs -f
