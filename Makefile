# Makefile for external-dns-technitium-webhook

# Determine the project root directory
ROOT_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

# Find the virtual environment directory within the project root
VENV_DIR := $(shell find $(ROOT_DIR) -maxdepth 2 -type d -name "venv" -o -name ".venv" | head -n 1)

# Default to a standard venv path if not found
ifeq ($(VENV_DIR),)
    VENV_DIR := $(ROOT_DIR)/.venv
endif

# Define Python and Pip executables from the virtual environment
VENV_PYTHON = $(VENV_DIR)/bin/python
VENV_PIP = $(VENV_DIR)/bin/pip

.PHONY: help install install-dev test test-cov lint format format-check type-check security clean docker-build docker-run check-deps all codeql-scan

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

codeql-scan: ## Run a comprehensive CodeQL security scan
	@echo "--- Creating CodeQL database ---"
	@codeql database create .codeql-db --language=python --command='make test' --overwrite --search-path=codeql/python-all --search-path=codeql/python-all
	@echo "\n--- Analyzing database with security-extended and security-and-quality suites ---"
	@codeql database analyze .codeql-db \
		/Users/drobson/.codeql/packages/codeql/python-queries/1.6.7/codeql-suites/python-security-extended.qls \
		/Users/drobson/.codeql/packages/codeql/python-queries/1.6.7/codeql-suites/python-security-and-quality.qls \
		--format=sarif-latest \
		--output=codeql-results-extended.sarif
	@echo "\n--- Scan complete. Results are in codeql-results-extended.sarif ---"

install: ## Install package
	$(VENV_PIP) install -e .

install-dev: ## Install package with development dependencies
	$(VENV_PIP) install -e ".[dev]"

test: ## Run tests
	$(VENV_PYTHON) -m pytest

test-cov: ## Run tests with coverage
	$(VENV_PYTHON) -m pytest --cov=external_dns_technitium_webhook --cov-report=html --cov-report=term

lint: ## Run linting
	$(VENV_PYTHON) -m ruff check .
	$(VENV_PYTHON) -m pyright

format: ## Format code
	$(VENV_PYTHON) -m ruff format .

format-check: ## Check code formatting
	$(VENV_PYTHON) -m ruff format --check .

type-check: ## Run type checking
	$(VENV_PYTHON) -m mypy external_dns_technitium_webhook
	$(VENV_PYTHON) -m pyright

security: ## Run security scans
	$(VENV_DIR)/bin/semgrep scan --config auto

check-deps: ## Check for outdated dependencies and vulnerabilities
	@echo "Checking dependencies..."
	@$(VENV_PYTHON) scripts/check_dependencies.py

clean: ## Clean up generated files
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf .pyright
	rm -rf htmlcov
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

docker-build: ## Build Docker image
	docker build -t external-dns-technitium-webhook:latest .

docker-run: ## Run Docker container
	docker run -p 3000:3000 \
		-e TECHNITIUM_URL=http://host.docker.internal:5380 \
		-e TECHNITIUM_USERNAME=admin \
		-e TECHNITIUM_PASSWORD=admin \
		-e ZONE=example.com \
		-e LOG_LEVEL=DEBUG \
		external-dns-technitium-webhook:latest

docker-compose-up: ## Start services with docker-compose
	docker-compose up -d

docker-compose-down: ## Stop services with docker-compose
	docker-compose down

docker-compose-logs: ## View docker-compose logs
	docker-compose logs -f

all: format lint type-check test ## Run all checks
