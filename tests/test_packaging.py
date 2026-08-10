"""The package's version is one string, not two that agree today (SPZ-44).

`__version__` is a published ledger field, so a `pyproject.toml` that restated it
would eventually let a committed ledger claim a version that was never released.
`[tool.hatch.version]` reads `_version.py`, and these tests keep it that way.
"""

from __future__ import annotations

import tomllib
from importlib.metadata import version
from pathlib import Path

from genai_corpus import __version__

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text())


def test_pyproject_declares_version_dynamic_rather_than_restating_it() -> None:
    config = _pyproject()

    assert "version" not in config["project"], "version must not be restated in pyproject.toml"
    assert "version" in config["project"]["dynamic"]


def test_pyproject_reads_the_version_from_the_package_itself() -> None:
    config = _pyproject()

    assert config["tool"]["hatch"]["version"]["path"] == "src/genai_corpus/_version.py"


def test_the_installed_distribution_reports_the_version_the_package_publishes() -> None:
    assert version("genai-corpus") == __version__
