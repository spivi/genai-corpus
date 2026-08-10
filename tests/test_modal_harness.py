"""Tests the harness's measurement arithmetic and constants only.

No Modal API call and no credential: `run_and_measure` is exercised with a plain
Python zero-argument callable, never `some_fn.remote(...)`, and `weights_volume()` /
`app` construction are themselves credential-free (SPZ-44's CI acceptance criterion).
"""

from __future__ import annotations

import time

import pytest

from genai_corpus.ledger import NOT_APPLICABLE
from genai_corpus.modal_harness import (
    HARDWARE_RATE_USD_PER_SECOND,
    WEIGHTS_VOLUME_MOUNT_PATH,
    WEIGHTS_VOLUME_NAME,
    capture_library_versions,
    run_and_measure,
    weights_volume,
)


def test_run_and_measure_on_cpu_hardware_fills_cpu_not_gpu() -> None:
    measurement = run_and_measure(lambda: 42, hardware="CPU")

    assert measurement.result == 42
    assert measurement.gpu_active_seconds == NOT_APPLICABLE
    assert isinstance(measurement.cpu_active_seconds, float)
    assert measurement.cpu_active_seconds >= 0


def test_run_and_measure_on_gpu_hardware_fills_gpu_not_cpu() -> None:
    measurement = run_and_measure(lambda: "ok", hardware="A10G")

    assert measurement.result == "ok"
    assert measurement.cpu_active_seconds == NOT_APPLICABLE
    assert isinstance(measurement.gpu_active_seconds, float)
    assert measurement.gpu_active_seconds >= 0


def test_run_and_measure_cost_is_elapsed_times_the_pinned_rate() -> None:
    measurement = run_and_measure(lambda: (time.sleep(0.02), None)[1], hardware="CPU")

    expected = measurement.cpu_active_seconds * HARDWARE_RATE_USD_PER_SECOND["CPU"]
    assert measurement.cost_usd == pytest.approx(expected)


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

    measurement = run_and_measure(lambda: payload, hardware="CPU")

    assert measurement.result is payload


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
    assert "CPU" in HARDWARE_RATE_USD_PER_SECOND


def test_capture_library_versions_reports_python_modal_and_genai_corpus() -> None:
    versions = capture_library_versions()

    assert set(versions) == {"python", "modal", "genai_corpus"}
    assert all(isinstance(v, str) and v for v in versions.values())
