from __future__ import annotations

from pathlib import Path

from genai_corpus import load_manifest, verify_checksums

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "corpus"
MANIFEST = FIXTURE_ROOT / "manifest.json"


def test_load_manifest_reads_all_fixture_assets() -> None:
    assets = load_manifest(MANIFEST)
    assert len(assets) == 4
    assert {asset.kind for asset in assets} == {"document"}
    assert all(asset.sha256 for asset in assets)


def test_verify_checksums_finds_no_mismatch_against_committed_fixture() -> None:
    assert verify_checksums(MANIFEST, FIXTURE_ROOT) == []


def test_verify_checksums_flags_a_tampered_asset(tmp_path: Path) -> None:
    tampered = tmp_path / "docs"
    tampered.mkdir()
    for asset in load_manifest(MANIFEST):
        (tampered / Path(asset.path).name).write_bytes(b"not the original bytes")
    mismatches = verify_checksums(MANIFEST, tmp_path)
    assert len(mismatches) == 4
