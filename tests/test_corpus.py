from __future__ import annotations

import json
from pathlib import Path

import pytest

from genai_corpus import CorpusAsset, load_manifest, verify_checksums

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "corpus"
MANIFEST = FIXTURE_ROOT / "manifest.json"


def _write_assets(dest_root: Path, assets: list[CorpusAsset]) -> None:
    """Copy fixture bytes for `assets` into `dest_root`, mirroring manifest paths."""
    for asset in assets:
        target = dest_root / asset.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((FIXTURE_ROOT / asset.path).read_bytes())


def test_load_manifest_reads_all_fixture_assets() -> None:
    assets = load_manifest(MANIFEST)

    assert len(assets) == 4
    assert {asset.kind for asset in assets} == {"document"}
    assert all(asset.sha256 for asset in assets)


def test_load_manifest_missing_file_raises_file_not_found_error(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.json"

    with pytest.raises(FileNotFoundError):
        load_manifest(missing)


def test_load_manifest_dict_instead_of_list_raises_type_error(tmp_path: Path) -> None:
    bad_manifest = tmp_path / "manifest.json"
    bad_manifest.write_text(json.dumps({"id": "doc-0001", "kind": "document"}))

    with pytest.raises(TypeError):
        load_manifest(bad_manifest)


def test_load_manifest_entry_missing_required_key_raises_key_error(tmp_path: Path) -> None:
    bad_manifest = tmp_path / "manifest.json"
    entry = {"id": "doc-0001", "kind": "document", "path": "x.txt"}  # no sha256
    bad_manifest.write_text(json.dumps([entry]))

    with pytest.raises(KeyError):
        load_manifest(bad_manifest)


def test_load_manifest_empty_list_returns_no_assets(tmp_path: Path) -> None:
    empty_manifest = tmp_path / "manifest.json"
    empty_manifest.write_text("[]")

    assets = load_manifest(empty_manifest)

    assert assets == []


def test_verify_checksums_finds_no_mismatch_against_committed_fixture() -> None:
    mismatches = verify_checksums(MANIFEST, FIXTURE_ROOT)

    assert mismatches == []


def test_verify_checksums_flags_a_tampered_asset(tmp_path: Path) -> None:
    tampered = tmp_path / "docs"
    tampered.mkdir()
    for asset in load_manifest(MANIFEST):
        (tampered / Path(asset.path).name).write_bytes(b"not the original bytes")

    mismatches = verify_checksums(MANIFEST, tmp_path)

    assert len(mismatches) == 4


def test_verify_checksums_partial_mismatch_flags_only_the_tampered_asset(
    tmp_path: Path,
) -> None:
    assets = load_manifest(MANIFEST)
    _write_assets(tmp_path, assets)
    tampered_asset = assets[0]
    (tmp_path / tampered_asset.path).write_bytes(b"tampered bytes")

    mismatches = verify_checksums(MANIFEST, tmp_path)

    assert mismatches == [tampered_asset.id]


def test_verify_checksums_missing_asset_file_is_reported_not_raised(
    tmp_path: Path,
) -> None:
    assets = load_manifest(MANIFEST)
    _write_assets(tmp_path, assets[1:])
    # assets[0]'s file is never written to tmp_path at all.

    mismatches = verify_checksums(MANIFEST, tmp_path)

    assert mismatches == [assets[0].id]
