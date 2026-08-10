"""Committed ledger-fixture guards (SPZ-44).

Two threats from the PRD's threat model, both enforced as assertions rather than
left to review: a ledger fixture is schema-valid (proving the hand-run's harness
output actually satisfies the contract it claims to), and it discloses nothing it
wasn't meant to publish — no local path, hostname, or credential-shaped string.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from genai_corpus.ledger import validate_ledger

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_FIXTURES_DIR = REPO_ROOT / "fixtures" / "ledgers"

# Known-sensitive strings from the machine SPZ-44's hand-run was executed on, checked
# against the committed fixture regardless of which machine runs this test — computing
# "the current machine's hostname" at test time would miss exactly the leak this guards.
_FORBIDDEN_SUBSTRINGS = ("/Users/", "Spivis-MacBook-Pro", "\\Users\\")
# Modal token IDs/secrets are shaped like `ak-...` / `as-...`.
_TOKEN_SHAPED = re.compile(r"\ba[ks]-[A-Za-z0-9]{20,}\b")


def _ledger_fixture_files() -> list[Path]:
    if not LEDGER_FIXTURES_DIR.exists():
        return []
    return sorted(LEDGER_FIXTURES_DIR.glob("*.json"))


def test_at_least_one_hand_run_ledger_fixture_is_committed() -> None:
    assert _ledger_fixture_files(), "SPZ-44 requires the Modal hand-run ledger as a fixture"


def test_ledger_fixtures_contain_no_local_path_or_hostname() -> None:
    for path in _ledger_fixture_files():
        text = path.read_text()
        for forbidden in _FORBIDDEN_SUBSTRINGS:
            assert forbidden not in text, f"{path.name}: contains {forbidden!r}"


def test_ledger_fixtures_contain_no_credential_shaped_token() -> None:
    for path in _ledger_fixture_files():
        match = _TOKEN_SHAPED.search(path.read_text())
        assert match is None, f"{path.name}: contains a credential-shaped token"


def test_ledger_fixtures_are_all_schema_valid() -> None:
    for path in _ledger_fixture_files():
        validate_ledger(json.loads(path.read_text()))
