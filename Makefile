.PHONY: help install clean format lint test pre-commit-install pre-commit-run check

VENV          := .venv
PYTHON        := $(VENV)/bin/python
PIP           := $(VENV)/bin/pip
BLACK         := $(VENV)/bin/black
RUFF          := $(VENV)/bin/ruff
PRE_COMMIT    := $(VENV)/bin/pre-commit
PYTEST        := $(VENV)/bin/pytest
STAMP         := $(VENV)/.install.stamp

help:  ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: $(STAMP)  ## Create venv and install dev dependencies (idempotent)

$(STAMP): pyproject.toml
	@test -d $(VENV) || python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@touch $(STAMP)

format: $(STAMP)  ## Run black
	$(BLACK) src tests

lint: $(STAMP)  ## Run ruff (lint only, never `ruff format`)
	$(RUFF) check src tests

test: $(STAMP)  ## Run pytest
	$(PYTEST)

pre-commit-install: $(STAMP)  ## Install git hooks
	$(PRE_COMMIT) install

pre-commit-run: $(STAMP)  ## Run pre-commit against all files
	$(PRE_COMMIT) run --all-files

check: lint test  ## Lint + test

clean:  ## Remove venv and caches
	rm -rf $(VENV) .pytest_cache .ruff_cache build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
