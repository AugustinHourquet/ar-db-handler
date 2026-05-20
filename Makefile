.PHONY: help install clean format lint test pre-commit-install pre-commit-run check

# ---------------------------------------------------------------------------
# Cross-platform setup.
#
# On Windows, cmd.exe is happiest with backslashes in direct path
# invocations, and venv binaries live in .venv\Scripts\. On Unix
# shells, it's forward slashes and .venv/bin/. We pick once at the top.
#
# Everything else is invoked as `$(PYTHON) -m <module>` so we only ever
# need ONE path to be correct (the venv's python) — pip, black, ruff,
# pytest, and pre-commit all support `-m`.
# ---------------------------------------------------------------------------

ifeq ($(OS),Windows_NT)
    PYTHON     := .venv\Scripts\python.exe
    PYTHON_SYS := python
else
    PYTHON     := .venv/bin/python
    PYTHON_SYS := python3
endif

STAMP := .venv/.install.stamp

help:  ## Show this help
	@$(PYTHON_SYS) -c "import re; [print(f'  {m.group(1):<22s} {m.group(2)}') for line in open('Makefile') for m in [re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)] if m]"

install: $(STAMP)  ## Create venv and install dev dependencies (idempotent)

$(STAMP): pyproject.toml
	@$(PYTHON_SYS) -c "import os,venv; (None if os.path.isdir('.venv') else venv.EnvBuilder(with_pip=True).create('.venv'))"
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"
	@$(PYTHON_SYS) -c "open(r'$(STAMP)','w').close()"

format: $(STAMP)  ## Run black
	$(PYTHON) -m black src tests

lint: $(STAMP)  ## Run ruff (lint only, never `ruff format`)
	$(PYTHON) -m ruff check src tests

test: $(STAMP)  ## Run pytest
	$(PYTHON) -m pytest

pre-commit-install: $(STAMP)  ## Install git hooks
	$(PYTHON) -m pre_commit install

pre-commit-run: $(STAMP)  ## Run pre-commit against all files
	$(PYTHON) -m pre_commit run --all-files

check: lint test  ## Lint + test

clean:  ## Remove venv and caches
	@$(PYTHON_SYS) -c "import shutil; [shutil.rmtree(p,ignore_errors=True) for p in ['.venv','.pytest_cache','.ruff_cache','build','dist']]"
	@$(PYTHON_SYS) -c "import shutil,os; [shutil.rmtree(os.path.join(r,d),ignore_errors=True) for r,ds,_ in os.walk('.') for d in ds if d=='__pycache__']"
	@$(PYTHON_SYS) -c "import shutil,glob; [shutil.rmtree(p,ignore_errors=True) for p in glob.glob('*.egg-info') + glob.glob('src/*.egg-info')]"
