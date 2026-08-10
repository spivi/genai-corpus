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

import pytest

from genai_corpus.ledger import NOT_APPLICABLE, validate_ledger
from genai_corpus.modal_harness import container_request, cpu_probe

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_FIXTURES_DIR = REPO_ROOT / "fixtures" / "ledgers"
HAND_RUN_FIXTURE = LEDGER_FIXTURES_DIR / "spz-44-hand-run.json"

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


def test_ledger_fixture_costs_are_re_derivable_from_their_own_provenance() -> None:
    """A published dollar figure must be recomputable later, not only re-asserted.

    Every fixture carries the billed seconds and the USD/second rate that priced them,
    with the rate's vintage in its unit string — so `cost = seconds x rate` is a check
    a reader can run against the committed file years after the price page changed.
    """
    for path in _ledger_fixture_files():
        ledger = validate_ledger(json.loads(path.read_text()))
        metrics = {metric.name: metric for metric in ledger.per_unit_metrics}
        assert "billed_container_seconds" in metrics, f"{path.name}: no billed-seconds row"
        rate = metrics["hardware_rate_usd_per_second"]
        assert "verified" in rate.unit, f"{path.name}: rate row states no verification date"
        expected = metrics["billed_container_seconds"].value * rate.value
        assert ledger.cost_per_result_usd == pytest.approx(expected)


def test_ledger_fixtures_record_what_the_container_asked_for() -> None:
    """The rate alone does not make a cost figure correctable.

    `HARDWARE_RATE_USD_PER_SECOND["CPU"]` prices a *full* core, and Modal bills
    `max(request, actual)`, so a container on the 0.125-core default is charged about
    an eighth of that plus memory. Without the request in the ledger, the only way to
    find that out is a README paragraph — the same provenance standard the rate row
    already meets, applied to the other factor.
    """
    for path in _ledger_fixture_files():
        ledger = validate_ledger(json.loads(path.read_text()))
        names = {metric.name for metric in ledger.per_unit_metrics}
        assert "cpu_request_cores" in names, f"{path.name}: no cpu-request row"
        assert "memory_request_mib" in names, f"{path.name}: no memory-request row"


def test_the_hand_run_fixture_request_rows_still_match_the_probe_function() -> None:
    """Re-derived from the decorated Function, not trusted as a committed literal.

    If someone gives `cpu_probe` an explicit `cpu=`/`memory=`, the committed ledger's
    request rows become wrong and the README's correction with them; this fails then.
    """
    ledger = validate_ledger(json.loads(HAND_RUN_FIXTURE.read_text()))
    metrics = {metric.name: metric.value for metric in ledger.per_unit_metrics}

    assert (metrics["cpu_request_cores"], metrics["memory_request_mib"]) == container_request(
        cpu_probe
    )


def test_ledger_fixtures_never_publish_an_unexplained_cpu_active_time_na() -> None:
    """Every Modal container has CPU cores and is billed for them, so a bare `n/a`
    on `cpu_active_seconds` claims something false.

    The harness times billed container span, not in-container compute; recording that
    span under `cpu_active_seconds` was the SPZ-44 review's P1. A committed fixture
    either carries a real active-time measurement or says why it does not.
    """
    for path in _ledger_fixture_files():
        ledger = validate_ledger(json.loads(path.read_text()))
        lanes = ["cpu_active_seconds"]
        if ledger.hardware not in (NOT_APPLICABLE, "CPU"):
            lanes.append("gpu_active_seconds")
        for name in lanes:
            if getattr(ledger, name) == NOT_APPLICABLE:
                assert name in ledger.not_applicable_reasons, f"{path.name}: {name} unexplained"
