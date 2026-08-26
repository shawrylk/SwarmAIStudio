.PHONY: all run dev start stop install test clean help

PYTHON ?= python3
PORT ?= 8080

help:
	@echo "Swarm AI Studio Commands:"
	@echo "  make run        - Run server in foreground (default)"
	@echo "  make dev        - Run server in interactive development mode"
	@echo "  make start      - Launch server in background daemon mode"
	@echo "  make stop       - Stop background server daemon"
	@echo "  make install    - Install Python package and dependencies"
	@echo "  make test       - Run full unit test suite"
	@echo "  make clean      - Clean cache and temporary build artifacts"

all: run

install:
	@echo "Installing dependencies..."
	$(PYTHON) -m pip install -r requirements.txt
	chmod +x bin/swarm-studio bin/qwen_oracle.sh scripts/*.sh

run:
	@$(PYTHON) bin/swarm-studio --port $(PORT)

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
