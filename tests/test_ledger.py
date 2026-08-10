from __future__ import annotations

from typing import Any

import pytest

from genai_corpus.ledger import (
    NOT_APPLICABLE,
    LedgerValidationError,
    ledger_from_json,
    ledger_to_dict,
    ledger_to_json,
    validate_ledger,
)

# A fully-measured ledger: every field concrete except the three that a unit with no
# metered API and no quality eval would legitimately mark not-applicable — proving the
# sentinel and real measurements coexist on one ledger, not just in isolation.
_VALID_LEDGER: dict[str, Any] = {
    "unit_id": "C5.7",
    "schema_version": "1.0",
    "measured_at": "2026-08-10T00:00:00+00:00",
    "library_versions": {"python": "3.12.13", "modal": "1.5.3"},
    "hardware": "A10G",
    "model_name": "llama-3-8b",
    "model_precision": "int8",
    "input_size_bytes": 1024,
    "output_size_bytes": 2048,
    "assets_processed_count": 10,
    "embedding_or_generation_calls_count": 10,
    "metered_tokens_count": NOT_APPLICABLE,
    "gpu_active_seconds": 12.5,
    "cpu_active_seconds": NOT_APPLICABLE,
    "storage_bytes": 4096,
    "egress_bytes": 0,
    "cache_hit_rate": 0.0,
    "cost_per_result_usd": 0.002,
    "cost_per_1000_results_usd": 2.0,
    "quality_metric_name": NOT_APPLICABLE,
    "quality_metric_value": NOT_APPLICABLE,
    "failure_rate": 0.0,
}

_ALL_NA_OVERRIDES: dict[str, Any] = {
    "hardware": NOT_APPLICABLE,
    "model_name": NOT_APPLICABLE,
    "model_precision": NOT_APPLICABLE,
    "input_size_bytes": NOT_APPLICABLE,
    "output_size_bytes": NOT_APPLICABLE,
    "assets_processed_count": NOT_APPLICABLE,
    "embedding_or_generation_calls_count": NOT_APPLICABLE,
    "metered_tokens_count": NOT_APPLICABLE,
    "gpu_active_seconds": NOT_APPLICABLE,
    "cpu_active_seconds": NOT_APPLICABLE,
    "storage_bytes": NOT_APPLICABLE,
    "egress_bytes": NOT_APPLICABLE,
    "cache_hit_rate": NOT_APPLICABLE,
    "cost_per_result_usd": NOT_APPLICABLE,
    "cost_per_1000_results_usd": NOT_APPLICABLE,
    "quality_metric_name": NOT_APPLICABLE,
    "quality_metric_value": NOT_APPLICABLE,
    "failure_rate": NOT_APPLICABLE,
}


def test_validate_ledger_accepts_a_fully_measured_ledger() -> None:
    ledger = validate_ledger(_VALID_LEDGER)

    assert ledger.hardware == "A10G"
    assert ledger.metered_tokens_count == NOT_APPLICABLE
    assert ledger.per_unit_metrics == ()


def test_validate_ledger_accepts_not_applicable_on_every_optional_field() -> None:
    data = {**_VALID_LEDGER, **_ALL_NA_OVERRIDES}

    ledger = validate_ledger(data)

    assert ledger.hardware == NOT_APPLICABLE
    assert ledger.failure_rate == NOT_APPLICABLE


@pytest.mark.parametrize("field_name", sorted(_VALID_LEDGER.keys()))
def test_validate_ledger_missing_any_field_raises_naming_it(field_name: str) -> None:
    data = dict(_VALID_LEDGER)
    del data[field_name]

    with pytest.raises(LedgerValidationError) as exc_info:
        validate_ledger(data)

    assert exc_info.value.field == field_name


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("hardware", 12),  # expects str
        ("input_size_bytes", "a lot"),  # expects int
        ("gpu_active_seconds", "twelve"),  # expects float
        ("library_versions", "python 3.12"),  # expects dict[str, str]
        ("input_size_bytes", True),  # bool must not satisfy int
        ("cost_per_result_usd", True),  # bool must not satisfy float
    ],
)
def test_validate_ledger_wrong_type_raises_naming_the_field(
    field_name: str, bad_value: Any
) -> None:
    data = {**_VALID_LEDGER, field_name: bad_value}

    with pytest.raises(LedgerValidationError) as exc_info:
        validate_ledger(data)

    assert exc_info.value.field == field_name


def test_validate_ledger_invented_field_raises_naming_it() -> None:
    data = {**_VALID_LEDGER, "gpu_seconds": 1.0}  # the unit-confusable name, not ours

    with pytest.raises(LedgerValidationError) as exc_info:
        validate_ledger(data)

    assert exc_info.value.field == "gpu_seconds"


def test_validate_ledger_int_satisfies_a_float_field() -> None:
    data = {**_VALID_LEDGER, "cost_per_result_usd": 0}

    ledger = validate_ledger(data)

    assert ledger.cost_per_result_usd == 0


def test_validate_ledger_per_unit_metrics_defaults_to_empty() -> None:
    ledger = validate_ledger(_VALID_LEDGER)

    assert ledger.per_unit_metrics == ()


def test_validate_ledger_per_unit_metrics_accepts_extra_rows() -> None:
    data = {
        **_VALID_LEDGER,
        "per_unit_metrics": [{"name": "tokens_per_dollar", "value": 500.0, "unit": "tokens/usd"}],
    }

    ledger = validate_ledger(data)

    assert ledger.per_unit_metrics[0].name == "tokens_per_dollar"
    assert ledger.per_unit_metrics[0].value == 500.0


def test_validate_ledger_per_unit_metric_missing_key_raises_naming_the_row() -> None:
    data = {**_VALID_LEDGER, "per_unit_metrics": [{"name": "x", "value": 1.0}]}

    with pytest.raises(LedgerValidationError) as exc_info:
        validate_ledger(data)

    assert exc_info.value.field == "per_unit_metrics[0]"


def test_validate_ledger_per_unit_metric_extra_key_raises_naming_the_row() -> None:
    data = {
        **_VALID_LEDGER,
        "per_unit_metrics": [{"name": "x", "value": 1.0, "unit": "u", "note": "extra"}],
    }

    with pytest.raises(LedgerValidationError) as exc_info:
        validate_ledger(data)

    assert exc_info.value.field == "per_unit_metrics[0]"


def test_validate_ledger_per_unit_metrics_not_a_list_raises() -> None:
    data = {**_VALID_LEDGER, "per_unit_metrics": {"name": "x", "value": 1.0, "unit": "u"}}

    with pytest.raises(LedgerValidationError) as exc_info:
        validate_ledger(data)

    assert exc_info.value.field == "per_unit_metrics"


def test_ledger_to_dict_round_trips_through_validate_ledger() -> None:
    ledger = validate_ledger(_VALID_LEDGER)

    rebuilt = validate_ledger(ledger_to_dict(ledger))

    assert rebuilt == ledger


def test_ledger_to_json_round_trips_through_ledger_from_json() -> None:
    ledger = validate_ledger(_VALID_LEDGER)

    rebuilt = ledger_from_json(ledger_to_json(ledger))

    assert rebuilt == ledger


def test_ledger_to_dict_emits_a_json_array_for_per_unit_metrics() -> None:
    data = {
        **_VALID_LEDGER,
        "per_unit_metrics": [{"name": "x", "value": 1.0, "unit": "u"}],
    }
    ledger = validate_ledger(data)

    payload = ledger_to_dict(ledger)

    assert payload["per_unit_metrics"] == [{"name": "x", "value": 1.0, "unit": "u"}]
