# ---------------------------------------------------------------------------
# ar-db-handler — Makefile (cross-platform: Unix + Windows cmd.exe)
#
# Bootstraps a project-local virtualenv at .venv/ and runs every target
# through it. No global pip installs, no need to activate the venv first.
#
# `make install` is idempotent via a stamp file (.venv/.installed) — it
# only re-runs pip when pyproject.toml or .pre-commit-config.yaml change.
#
# Cross-platform notes
# --------------------
# Windows `make` (Chocolatey / scoop / GnuWin32 / win-builds) runs recipe
# lines through cmd.exe, which has two quirks that bit us:
#
#   1. cmd.exe interprets forward slashes as switch markers, so a path
#      like `.venv/Scripts/python.exe` is parsed as `.venv` plus the
#      switches `/Scripts` and `/python.exe`, producing:
#         '.venv' n'est pas reconnu en tant que commande interne...
#      Fix: define paths with forward slashes (portable) and translate
#      to backslashes via $(subst /,$(BS),...) on Windows only.
#
#   2. cmd.exe has no `rm`, `find`, `test`, or `touch`. We delegate FS
#      ops to scripts/make_helpers.py — pathlib / shutil work the same
#      on every OS.
#
# `make clean-venv` cannot delete the venv that's currently activated —
# Windows locks python.exe while it's running. Run `deactivate` first.
# ---------------------------------------------------------------------------

.DEFAULT_GOAL := help

# Allow override:  make VENV=.venv-dev install
VENV ?= .venv

# Cross-platform settings.
# Windows: paths must use backslashes for cmd.exe; python is `python`;
#          venv binaries live under Scripts/ and end in .exe.
# Unix:    paths use forward slashes; python is `python3`; venv binaries
#          live under bin/ with no extension.
ifeq ($(OS),Windows_NT)
    VENV_BIN := $(VENV)/Scripts
    PYTHON_BOOTSTRAP := python
    EXE := .exe
    # The classic make idiom for embedding a single literal backslash:
    # $(strip ...) collapses trailing spaces, leaving just `\`.
    BS := $(strip \ )
    # Convert forward slashes to backslashes for any path we hand to cmd.exe.
    fix_path = $(subst /,$(BS),$(1))
else
    VENV_BIN := $(VENV)/bin
    PYTHON_BOOTSTRAP := python3
    EXE :=
    fix_path = $(1)
endif

# Portable (forward-slash) path definitions. We pass them through
# $(fix_path) at each use-site so the variables themselves stay simple
# and the Windows-only translation is contained to one place.
PYTHON := $(call fix_path,$(VENV_BIN)/python$(EXE))
PIP := $(PYTHON) -m pip
STAMP := $(call fix_path,$(VENV)/.installed)
HELPERS := $(call fix_path,scripts/make_helpers.py)
PRECOMMIT := $(call fix_path,$(VENV_BIN)/pre-commit$(EXE))

.PHONY: help install install-gcs format lint test setup-check pre-commit-install \
        clean clean-venv

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
help:
	@echo ar-db-handler -- Make targets
	@echo.
	@echo   install              Create .venv and install the package + dev deps.
	@echo                        Idempotent (stamp file at $(STAMP)).
	@echo   install-gcs          Install + the optional [gcs] extra.
	@echo   format               Run black + ruff --fix on src tests scripts.
	@echo   lint                 Run ruff check + black --check on src tests scripts.
	@echo   test                 Run pytest.
	@echo   setup-check          Import the package and print its version.
	@echo   pre-commit-install   Install the git pre-commit hooks.
	@echo   clean                Remove build artefacts and caches (keeps the venv).
	@echo   clean-venv           Remove the venv directory itself.
	@echo                        (Windows: run `deactivate` first if the venv is active.)

# ---------------------------------------------------------------------------
# Install — create venv and editable-install with dev deps
#
# The stamp file makes the target idempotent: a subsequent `make install`
# is a no-op unless pyproject.toml or .pre-commit-config.yaml changed.
#
# `python -m venv` is itself idempotent — it will not destroy an existing
# venv, so no test-d guard is needed (and `test` does not exist on cmd.exe).
# ---------------------------------------------------------------------------
install: $(STAMP)

$(STAMP): pyproject.toml .pre-commit-config.yaml
	@echo ">>> Bootstrapping virtualenv at $(VENV) ..."
	@$(PYTHON_BOOTSTRAP) -m venv $(VENV)
	@$(PIP) install --upgrade pip wheel
	@$(PIP) install -e ".[dev]"
	@$(PYTHON_BOOTSTRAP) $(HELPERS) stamp $(STAMP)
	@echo ">>> $(VENV) is ready."

# Convenience: install + the optional GCS extra so sync_companies() works.
install-gcs: install
	@$(PIP) install -e ".[gcs]"

# ---------------------------------------------------------------------------
# Dev tasks — every target runs through the venv's Python directly
# ---------------------------------------------------------------------------
format: install
	@$(PYTHON) -m black src tests scripts
	@$(PYTHON) -m ruff check --fix src tests scripts

lint: install
	@$(PYTHON) -m ruff check src tests scripts
	@$(PYTHON) -m black --check src tests scripts

test: install
	@$(PYTHON) -m pytest

setup-check: install
	@$(PYTHON) -c "import ar_db_handler; print('ar_db_handler version:', ar_db_handler.__version__)"

pre-commit-install: install
	@$(PRECOMMIT) install

# ---------------------------------------------------------------------------
# Cleaning — delegated to scripts/make_helpers.py so it works on Windows.
#
# `clean` does not depend on $(STAMP) — it must work even when the venv
# has been wiped (which is precisely when users reach for `make clean`).
# We use $(PYTHON_BOOTSTRAP) (system Python) rather than $(PYTHON) (venv
# Python) for the same reason: `make clean` shouldn't require a venv.
# ---------------------------------------------------------------------------
clean:
	@$(PYTHON_BOOTSTRAP) $(HELPERS) clean

clean-venv:
	@$(PYTHON_BOOTSTRAP) $(HELPERS) clean-venv $(VENV)