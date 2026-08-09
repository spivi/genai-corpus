"""Fixture-size guard (SPZ-43): enforced as an assertion, not a README note.

GitHub's LFS free tier is roughly 1 GB against the real corpus's 5 GB cap, so no
corpus media may ever enter this git history. This test is the local half of that
enforcement; CI runs the same assertion against a clean clone.
"""

from __future__ import annotations

from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "corpus"
MAX_FIXTURE_BYTES = 5 * 1024 * 1024  # 5 MB

# Extensions the repo's .gitignore excludes as "media" — kept in sync with .gitignore's
# Images/Audio/Video sections. A fixture file with one of these extensions would mean
# the fixture depends on bytes .gitignore would otherwise refuse to commit.
IGNORED_MEDIA_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".svg", ".heic", ".psd",
    ".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v",
}


def _fixture_files() -> list[Path]:
    return [p for p in FIXTURE_ROOT.rglob("*") if p.is_file()]


def test_fixture_corpus_is_under_five_megabytes() -> None:
    total = sum(p.stat().st_size for p in _fixture_files())
    assert total < MAX_FIXTURE_BYTES, f"fixture corpus is {total} bytes, over the 5 MB cap"


def test_fixture_corpus_contains_no_ignored_media_extension() -> None:
    offenders = [p for p in _fixture_files() if p.suffix.lower() in IGNORED_MEDIA_EXTENSIONS]
    assert offenders == [], f"fixture corpus contains ignored media extensions: {offenders}"
