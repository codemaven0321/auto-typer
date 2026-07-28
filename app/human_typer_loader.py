"""Load the upstream human_typer package despite its broken absolute import."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _find_package_dir() -> Path:
    import site

    search = []
    try:
        search.extend(Path(p) for p in site.getsitepackages())
    except Exception:
        pass
    try:
        search.append(Path(site.getusersitepackages()))
    except Exception:
        pass
    # Also check sys.path entries
    search.extend(Path(p) for p in sys.path if p)

    for base in search:
        candidate = base / "human_typer"
        if (candidate / "human_typer.py").exists() and (
            candidate / "keyboard_helper.py"
        ).exists():
            return candidate

    raise ImportError(
        "human_typer is not installed. Run: pip install -r requirements.txt"
    )


def load_human_typer():
    """Return the Human_typer class from the installed package."""
    pkg_dir = _find_package_dir()

    if "keyboard_helper" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "keyboard_helper", pkg_dir / "keyboard_helper.py"
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        sys.modules["keyboard_helper"] = module

    if "human_typer_core" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "human_typer_core", pkg_dir / "human_typer.py"
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        sys.modules["human_typer_core"] = module

    return sys.modules["human_typer_core"].Human_typer


Human_typer = load_human_typer()
