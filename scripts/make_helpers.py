"""
Cross-platform file-system helpers invoked by the Makefile.

Why this file exists
--------------------
Windows ``make`` (the one shipped via Chocolatey, scoop, or GnuWin32)
runs recipe lines through ``cmd.exe``, not bash. That means Unix
built-ins like ``rm``, ``find``, ``test`` and ``touch`` fail with
``CreateProcess … Le fichier spécifié est introuvable.`` (or the
English equivalent) because there is no executable named ``rm.exe``
on a stock Windows install.

Rather than branch every recipe on ``$(OS)``, the Makefile delegates
each file-system operation to this script. Python is already required
by the project, ``pathlib``/``shutil`` work identically on every OS,
and the recipes stay readable.

Usage
-----
::

    python scripts/make_helpers.py clean
    python scripts/make_helpers.py clean-venv .venv
    python scripts/make_helpers.py stamp .venv/.installed
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Paths cleaned by `clean` — same set the old Unix recipe targeted.
CLEAN_TOPLEVEL = ("build", "dist", ".pytest_cache", ".ruff_cache")

# Globs cleaned by `clean` — these use Path.rglob so they don't depend on the
# shell's globbing behaviour (cmd.exe in particular does not expand `*`).
CLEAN_GLOBS = (
    "*.egg-info",  # at the repo root (e.g. ar_db_handler.egg-info)
    "src/*.egg-info",  # under src/ when using the src-layout
)

# Recursive globs for in-tree clutter that pip/pytest scatter around.
CLEAN_RGLOBS = (
    "__pycache__",  # directories
    "*.pyc",  # files
)


def _rm(path: Path) -> None:
    """Delete ``path`` — file, symlink, or directory — without complaint."""
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
    except FileNotFoundError:
        # Already gone — that's the desired end state.
        return
    except OSError as exc:
        # On Windows, files held open by another process raise here.
        # Print but don't fail the whole make target.
        print(f"  (could not remove {path}: {exc})", file=sys.stderr)


def cmd_clean() -> int:
    """Remove build artefacts and caches. Idempotent — never errors out."""
    removed = 0

    for name in CLEAN_TOPLEVEL:
        p = REPO_ROOT / name
        if p.exists() or p.is_symlink():
            _rm(p)
            removed += 1

    for pattern in CLEAN_GLOBS:
        for p in REPO_ROOT.glob(pattern):
            _rm(p)
            removed += 1

    for pattern in CLEAN_RGLOBS:
        for p in REPO_ROOT.rglob(pattern):
            # Skip anything inside .venv — that's clean-venv's job, and
            # walking into it slows us down for no benefit.
            if any(part.startswith(".venv") for part in p.relative_to(REPO_ROOT).parts):
                continue
            _rm(p)
            removed += 1

    print(f"clean: removed {removed} path(s).")
    return 0


def cmd_clean_venv(venv_path: str) -> int:
    """Remove the venv directory."""
    p = REPO_ROOT / venv_path
    if p.exists():
        _rm(p)
        print(f"clean-venv: removed {p}")
    else:
        print(f"clean-venv: nothing at {p}")
    return 0


def cmd_stamp(stamp_path: str) -> int:
    """Touch the install stamp file (cross-platform equivalent of `touch`)."""
    p = REPO_ROOT / stamp_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch(exist_ok=True)
    return 0


COMMANDS = {
    "clean": cmd_clean,
    "clean-venv": cmd_clean_venv,
    "stamp": cmd_stamp,
}


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in COMMANDS:
        print(
            f"usage: python {Path(argv[0]).name} {{{'|'.join(COMMANDS)}}} [args...]",
            file=sys.stderr,
        )
        return 2

    cmd = COMMANDS[argv[1]]
    return cmd(*argv[2:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
