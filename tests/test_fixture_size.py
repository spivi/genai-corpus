"""Fixture-size guard (SPZ-43): enforced as an assertion, not a README note.

GitHub's LFS free tier is roughly 1 GB against the real corpus's 5 GB cap, so no
corpus media may ever enter this git history. This test is the local half of that
enforcement; CI runs the same assertion against a clean clone.

The ignored-extension list is parsed straight out of `.gitignore` rather than
hand-duplicated here, so the two can never drift apart.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "fixtures" / "corpus"
GITIGNORE = REPO_ROOT / ".gitignore"
MAX_FIXTURE_BYTES = 5 * 1024 * 1024  # 5 MB


def _ignored_media_extensions() -> set[str]:
    """Parse simple `*.ext` patterns out of `.gitignore`.

    Only bare `*.ext` lines are extension patterns; directory rules (`.venv/`),
    dotfile rules (`.DS_Store`) and comments don't match and are skipped.
    """
    extensions: set[str] = set()
    for line in GITIGNORE.read_text().splitlines():
        pattern = line.strip()
        if pattern.startswith("*.") and "/" not in pattern:
            extensions.add(pattern.removeprefix("*").lower())
    return extensions


def _fixture_files() -> list[Path]:
    return [p for p in FIXTURE_ROOT.rglob("*") if p.is_file()]


def test_fixture_corpus_is_under_five_megabytes() -> None:
    total = sum(p.stat().st_size for p in _fixture_files())
    assert total < MAX_FIXTURE_BYTES, f"fixture corpus is {total} bytes, over the 5 MB cap"


def test_fixture_corpus_contains_no_ignored_media_extension() -> None:
    ignored = _ignored_media_extensions()
    offenders = [p for p in _fixture_files() if p.suffix.lower() in ignored]
    assert offenders == [], f"fixture corpus contains ignored media extensions: {offenders}"
