"""Tests the harness's measurement arithmetic, rate table and ledger seam only.

No Modal API call and no credential: `run_and_measure` is exercised with a plain
Python zero-argument callable, never `some_fn.remote(...)`, and `weights_volume()` /
`app` construction are themselves credential-free (SPZ-44's CI acceptance criterion).
"""

from __future__ import annotations

import time
from datetime import date, timedelta

import modal
import pytest

from genai_corpus.ledger import NOT_APPLICABLE, LedgerValidationError
from genai_corpus.modal_harness import (
    CPU_HARDWARE,
    HARDWARE_RATE_USD_PER_SECOND,
    RATE_TABLE_MAX_AGE_DAYS,
    RATE_TABLE_VERIFIED_ON,
    WEIGHTS_VOLUME_MOUNT_PATH,
    WEIGHTS_VOLUME_NAME,
    HardwareMismatchError,
    capture_library_versions,
    hardware_from_function,
    ledger_from_measurement,
    rate_table_age_days,
    resolve_hardware_rate,
    run_and_measure,
    weights_volume,
)

_probe_app = modal.App("genai-corpus-harness-tests")


@_probe_app.function()
def _cpu_only() -> int:
    return 1


@_probe_app.function(gpu="H100")
def _one_h100() -> int:
    return 1


@_probe_app.function(gpu="H100:2")
def _two_h100() -> int:
    return 1


def test_run_and_measure_reports_billed_container_seconds_not_active_time() -> None:
    measurement = run_and_measure(lambda: 42, hardware=CPU_HARDWARE)

    assert measurement.result == 42
    assert isinstance(measurement.billed_container_seconds, float)
    assert measurement.billed_container_seconds >= 0
    # The span includes cold start, scheduling and RPC, so it is not active compute:
    # nothing on a measurement may be read as GPU/CPU active seconds.
    assert not hasattr(measurement, "gpu_active_seconds")
    assert not hasattr(measurement, "cpu_active_seconds")


def test_run_and_measure_cost_is_billed_seconds_times_the_pinned_rate() -> None:
    measurement = run_and_measure(lambda: (time.sleep(0.02), None)[1], hardware=CPU_HARDWARE)

    expected = measurement.billed_container_seconds * HARDWARE_RATE_USD_PER_SECOND[CPU_HARDWARE]
    assert measurement.cost_usd == pytest.approx(expected)
    assert measurement.rate_usd_per_second == HARDWARE_RATE_USD_PER_SECOND[CPU_HARDWARE]


def test_run_and_measure_unknown_hardware_raises_before_calling() -> None:
    called = False

    def call() -> int:
        nonlocal called
        called = True
        return 1

    with pytest.raises(ValueError, match="unknown hardware"):
        run_and_measure(call, hardware="quantum-annealer")

    assert called is False


def test_run_and_measure_propagates_the_calls_return_value_unchanged() -> None:
    payload = {"tokens": 10, "cached": True}

    measurement = run_and_measure(lambda: payload, hardware=CPU_HARDWARE)

    assert measurement.result is payload


def test_run_and_measure_rejects_hardware_the_function_spec_contradicts() -> None:
    called = False

    def call() -> int:
        nonlocal called
        called = True
        return 1

    with pytest.raises(HardwareMismatchError, match="gpu spec is 'H100'"):
        run_and_measure(call, hardware="T4", function=_one_h100)

    assert called is False


def test_run_and_measure_accepts_hardware_the_function_spec_agrees_with() -> None:
    measurement = run_and_measure(lambda: 1, hardware="H100", function=_one_h100)

    assert measurement.hardware == "H100"


def test_hardware_from_function_reads_the_gpu_spec() -> None:
    assert hardware_from_function(_cpu_only) == CPU_HARDWARE
    assert hardware_from_function(_one_h100) == "H100"
    assert hardware_from_function(_two_h100) == "H100:2"


def test_resolve_hardware_rate_prices_a_multi_gpu_spec_by_its_count() -> None:
    assert resolve_hardware_rate("H100:2") == pytest.approx(
        2 * HARDWARE_RATE_USD_PER_SECOND["H100"]
    )


@pytest.mark.parametrize("spec", ["H100:many", "H100:0", "H100:-2", "H100:", "H100:1.5"])
def test_resolve_hardware_rate_rejects_a_malformed_gpu_count(spec: str) -> None:
    """`"H100:"` belongs in this list. It used to price as one GPU: the branch tested
    the count text, and an empty string is falsy, so a truncated spec silently became
    the single-GPU rate while every other malformed count was rejected."""
    with pytest.raises(ValueError, match="bad GPU count"):
        resolve_hardware_rate(spec)


def test_weights_volume_mount_path_is_an_absolute_container_path() -> None:
    assert WEIGHTS_VOLUME_MOUNT_PATH.startswith("/")
    assert WEIGHTS_VOLUME_NAME


def test_weights_volume_constructs_without_a_credential() -> None:
    volume = weights_volume()

    assert volume is not None


def test_hardware_rate_table_has_no_negative_or_zero_rates() -> None:
    assert HARDWARE_RATE_USD_PER_SECOND
    assert all(rate > 0 for rate in HARDWARE_RATE_USD_PER_SECOND.values())


def test_hardware_rate_table_includes_cpu() -> None:
    assert CPU_HARDWARE in HARDWARE_RATE_USD_PER_SECOND


def test_hardware_rate_table_keys_are_modal_gpu_spec_strings() -> None:
    """Modal's published label is `A10`, not `A10G` — a key it never emits is dead."""
    assert "A10G" not in HARDWARE_RATE_USD_PER_SECOND
    assert "A10" in HARDWARE_RATE_USD_PER_SECOND


def test_rate_table_is_not_stale() -> None:
    """A price is a dated fact. Past the window, re-verify against modal.com/pricing.

    This failing is not a bug in the code: re-check every rate in
    `HARDWARE_RATE_USD_PER_SECOND`, then move `RATE_TABLE_VERIFIED_ON` to today.
    """
    age = rate_table_age_days()

    assert age <= RATE_TABLE_MAX_AGE_DAYS, (
        f"rate table verified {age} days ago ({RATE_TABLE_VERIFIED_ON.isoformat()}); "
        f"re-verify against https://modal.com/pricing"
    )


def test_rate_table_age_is_measured_from_the_verification_date() -> None:
    assert rate_table_age_days(RATE_TABLE_VERIFIED_ON) == 0
    assert rate_table_age_days(RATE_TABLE_VERIFIED_ON + timedelta(days=7)) == 7


def test_rate_table_verified_on_is_a_real_past_date() -> None:
    assert isinstance(RATE_TABLE_VERIFIED_ON, date)
    assert date.today() >= RATE_TABLE_VERIFIED_ON


def test_capture_library_versions_reports_python_modal_and_genai_corpus() -> None:
    versions = capture_library_versions()

    assert set(versions) == {"python", "modal", "genai_corpus"}
    assert all(isinstance(v, str) and v for v in versions.values())


def test_capture_library_versions_records_the_libraries_a_unit_names() -> None:
    versions = capture_library_versions({"torch": "2.4.1", "bitsandbytes": "0.43.1"})

    assert versions["torch"] == "2.4.1"
    assert versions["bitsandbytes"] == "0.43.1"
    assert versions["python"]


def test_capture_library_versions_refuses_to_let_extras_shadow_measured_keys() -> None:
    with pytest.raises(ValueError, match="may not shadow"):
        capture_library_versions({"modal": "9.9.9"})


def test_ledger_from_measurement_never_files_billed_time_as_active_time() -> None:
    """The SPZ-44 review's P1: the billed span is not CPU-active time, so it is not
    written into a field that says it is."""
    measurement = run_and_measure(lambda: 1, hardware=CPU_HARDWARE)

    ledger = ledger_from_measurement(measurement, unit_id="T-1")

    assert ledger.cpu_active_seconds == NOT_APPLICABLE
    assert ledger.gpu_active_seconds == NOT_APPLICABLE
    assert measurement.billed_container_seconds not in (
        ledger.cpu_active_seconds,
        ledger.gpu_active_seconds,
    )
    assert "not measured" in ledger.not_applicable_reasons["cpu_active_seconds"]


def test_ledger_from_measurement_leaves_gpu_time_bare_na_on_cpu_hardware() -> None:
    """A CPU container has no GPU, so "not measured" would be the wrong explanation."""
    measurement = run_and_measure(lambda: 1, hardware=CPU_HARDWARE)

    ledger = ledger_from_measurement(measurement, unit_id="T-1")

    assert "gpu_active_seconds" not in ledger.not_applicable_reasons


def test_ledger_from_measurement_explains_cpu_time_on_gpu_hardware_too() -> None:
    """A GPU container has CPU cores and is billed for them: "n/a" there is false."""
    measurement = run_and_measure(lambda: 1, hardware="H100")

    ledger = ledger_from_measurement(measurement, unit_id="T-1")

    assert "not measured" in ledger.not_applicable_reasons["cpu_active_seconds"]
    assert "not measured" in ledger.not_applicable_reasons["gpu_active_seconds"]


def test_ledger_from_measurement_carries_the_billed_seconds_and_rate_provenance() -> None:
    measurement = run_and_measure(lambda: 1, hardware=CPU_HARDWARE)

    ledger = ledger_from_measurement(measurement, unit_id="T-1")

    metrics = {metric.name: metric for metric in ledger.per_unit_metrics}
    assert metrics["billed_container_seconds"].value == measurement.billed_container_seconds
    assert metrics["hardware_rate_usd_per_second"].value == measurement.rate_usd_per_second
    assert RATE_TABLE_VERIFIED_ON.isoformat() in metrics["hardware_rate_usd_per_second"].unit


def test_ledger_from_measurement_divides_cost_across_the_runs_results() -> None:
    measurement = run_and_measure(lambda: 1, hardware=CPU_HARDWARE)

    ledger = ledger_from_measurement(measurement, unit_id="T-1", results=4)

    assert ledger.cost_per_result_usd == pytest.approx(measurement.cost_usd / 4)
    assert ledger.cost_per_1000_results_usd == pytest.approx(measurement.cost_usd / 4 * 1000)


def test_ledger_from_measurement_rejects_a_result_count_below_one() -> None:
    measurement = run_and_measure(lambda: 1, hardware=CPU_HARDWARE)

    with pytest.raises(ValueError, match="results must be at least 1"):
        ledger_from_measurement(measurement, unit_id="T-1", results=0)


def test_ledger_from_measurement_lets_the_caller_supply_measured_active_time() -> None:
    measurement = run_and_measure(lambda: 1, hardware=CPU_HARDWARE)

    ledger = ledger_from_measurement(measurement, unit_id="T-1", cpu_active_seconds=0.015)

    assert ledger.cpu_active_seconds == 0.015
    # The default reason is dropped, not left contradicting a measured value.
    assert "cpu_active_seconds" not in ledger.not_applicable_reasons


def test_ledger_from_measurement_appends_caller_metrics_after_the_provenance_rows() -> None:
    measurement = run_and_measure(lambda: 1, hardware=CPU_HARDWARE)

    ledger = ledger_from_measurement(
        measurement,
        unit_id="T-1",
        per_unit_metrics=[{"name": "tokens_per_dollar", "value": 5.0, "unit": "tokens/usd"}],
    )

    names = [metric.name for metric in ledger.per_unit_metrics]
    assert names == [
        "billed_container_seconds",
        "hardware_rate_usd_per_second",
        "tokens_per_dollar",
    ]


def test_ledger_from_measurement_emits_a_schema_valid_ledger() -> None:
    measurement = run_and_measure(lambda: 1, hardware=CPU_HARDWARE)

    ledger = ledger_from_measurement(measurement, unit_id="T-1", assets_processed_count=1)

    assert ledger.unit_id == "T-1"
    assert ledger.hardware == CPU_HARDWARE
    assert ledger.library_versions["genai_corpus"]


def test_ledger_from_measurement_refuses_a_hardware_that_contradicts_the_measurement() -> None:
    """`**fields` used to win outright, so `hardware="H100"` on a CPU measurement
    published a GPU ledger priced at the CPU rate — and, because the lane logic reads
    the same field, one whose GPU lane claimed it was measured and simply missing."""
    measurement = run_and_measure(lambda: 1, hardware=CPU_HARDWARE)

    with pytest.raises(ValueError, match="contradicts the measurement"):
        ledger_from_measurement(measurement, unit_id="T-1", hardware="H100")


def test_ledger_from_measurement_accepts_a_hardware_that_restates_the_measurement() -> None:
    """Refusing agreement would be noise: what is refused is disagreement."""
    measurement = run_and_measure(lambda: 1, hardware=CPU_HARDWARE)

    ledger = ledger_from_measurement(measurement, unit_id="T-1", hardware=CPU_HARDWARE)

    assert ledger.hardware == CPU_HARDWARE
    assert "gpu_active_seconds" not in ledger.not_applicable_reasons


def test_ledger_from_measurement_rejects_a_bad_caller_field_rather_than_emitting_it() -> None:
    measurement = run_and_measure(lambda: 1, hardware=CPU_HARDWARE)

    with pytest.raises(LedgerValidationError) as exc_info:
        ledger_from_measurement(measurement, unit_id="T-1", assets_processed_count="a few")

    assert exc_info.value.field == "assets_processed_count"
