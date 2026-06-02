from __future__ import annotations

from pathlib import Path


MARKER_DIR = ".agent-buffet"


def find_project_root(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / MARKER_DIR).is_dir():
            return candidate
    return None


def project_root(start: Path | None = None) -> Path:
    found = find_project_root(start)
    if found is None:
        return (start or Path.cwd()).resolve()
    return found


def require_project_root(start: Path | None = None) -> Path:
    found = find_project_root(start)
    if found is None:
        raise RuntimeError("No Agent Buffet project found. Run `kab init orbit-wars` first.")
    return found


def display_path(path: Path, root: Path | None = None) -> str:
    base = root or find_project_root(path) or Path.cwd()
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path)
