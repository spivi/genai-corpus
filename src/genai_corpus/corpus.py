"""Corpus manifest loading and checksum verification.

The real ~5 GB frozen corpus (`SPZ-45`) is a Hugging Face dataset, pinned by version in
each unit's cost ledger and never committed here. This module only knows how to read a
`manifest.json` (a flat list of asset records) and check each asset's bytes against its
recorded `sha256` — the same shape the real corpus manifest will use, exercised here
against the tiny fixture in `fixtures/corpus/`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CorpusAsset:
    """One row of a corpus manifest."""

    id: str
    kind: str
    path: str
    tags: tuple[str, ...]
    sha256: str


def load_manifest(manifest_path: str | Path) -> list[CorpusAsset]:
    """Read a `manifest.json` into a list of `CorpusAsset` records."""
    data = json.loads(Path(manifest_path).read_text())
    return [
        CorpusAsset(
            id=item["id"],
            kind=item["kind"],
            path=item["path"],
            tags=tuple(item.get("tags", [])),
            sha256=item["sha256"],
        )
        for item in data
    ]


def verify_checksums(manifest_path: str | Path, corpus_root: str | Path) -> list[str]:
    """Return the ids of assets whose on-disk sha256 doesn't match the manifest."""
    root = Path(corpus_root)
    mismatches: list[str] = []
    for asset in load_manifest(manifest_path):
        digest = hashlib.sha256((root / asset.path).read_bytes()).hexdigest()
        if digest != asset.sha256:
            mismatches.append(asset.id)
    return mismatches
