from __future__ import annotations

from typing import Any

import pytest

from genai_corpus.ledger import (
    LINE_ITEM_FIELDS,
    NOT_APPLICABLE,
    ROW_ORDER,
    SCHEMA_VERSION,
    LedgerValidationError,
    ledger_from_json,
    ledger_to_dict,
    ledger_to_json,
    validate_ledger,
)
from genai_corpus.ledger_table import parse_ledger_markdown_table

# A fully-measured ledger: every field concrete except the three that a unit with no
# metered API and no quality eval would legitimately mark not-applicable — proving the
# sentinel and real measurements coexist on one ledger, not just in isolation.
_VALID_LEDGER: dict[str, Any] = {
    "unit_id": "C5.7",
    "schema_version": SCHEMA_VERSION,
    "measured_at": "2026-08-10T00:00:00+00:00",
    "library_versions": {"python": "3.12.13", "modal": "1.5.3"},
    "hardware": "A10",
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

_ALL_NA_OVERRIDES: dict[str, Any] = dict.fromkeys(LINE_ITEM_FIELDS, NOT_APPLICABLE)


def test_validate_ledger_accepts_a_fully_measured_ledger() -> None:
    ledger = validate_ledger(_VALID_LEDGER)

    assert ledger.hardware == "A10"
    assert ledger.metered_tokens_count == NOT_APPLICABLE
    assert ledger.per_unit_metrics == ()
    assert ledger.not_applicable_reasons == {}


def test_validate_ledger_accepts_not_applicable_on_every_optional_field() -> None:
    data = {**_VALID_LEDGER, **_ALL_NA_OVERRIDES}

    ledger = validate_ledger(data)

    assert ledger.hardware == NOT_APPLICABLE
    assert ledger.failure_rate == NOT_APPLICABLE


def test_row_order_covers_exactly_the_mandated_line_items() -> None:
    """`ROW_ORDER` is the contract's label list, so it may not drift from the fields."""
    assert len(ROW_ORDER) == 18
    assert set(LINE_ITEM_FIELDS) < set(_VALID_LEDGER)
    assert len({label for _, label in ROW_ORDER}) == len(ROW_ORDER)


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


def test_validate_ledger_reports_every_bad_field_not_only_the_first() -> None:
    """One call, one exception, every fault — not one re-run per mistake."""
    data = {**_VALID_LEDGER, "hardware": 12, "input_size_bytes": "a lot"}
    del data["failure_rate"]

    with pytest.raises(LedgerValidationError) as exc_info:
        validate_ledger(data)

    reported = {name for name, _ in exc_info.value.problems}
    assert reported == {"failure_rate", "hardware", "input_size_bytes"}
    assert exc_info.value.field == "failure_rate"  # the first, kept for callers
    for name in reported:
        assert name in str(exc_info.value)


def test_validate_ledger_int_satisfies_a_float_field() -> None:
    data = {**_VALID_LEDGER, "cost_per_result_usd": 0}

    ledger = validate_ledger(data)

    assert ledger.cost_per_result_usd == 0


def test_validate_ledger_rejects_an_unimplemented_schema_version() -> None:
    data = {**_VALID_LEDGER, "schema_version": "99.0"}

    with pytest.raises(LedgerValidationError) as exc_info:
        validate_ledger(data)

    assert exc_info.value.field == "schema_version"
    assert "unsupported version" in str(exc_info.value)


def test_validate_ledger_rejects_a_line_break_in_a_string_field() -> None:
    data = {**_VALID_LEDGER, "model_name": "llama-3\n| injected | row |"}

    with pytest.raises(LedgerValidationError) as exc_info:
        validate_ledger(data)

    assert exc_info.value.field == "model_name"


#: Every character `str.splitlines()` breaks on beyond `\r` and `\n`. The parser in
#: `ledger_table` splits with `str.splitlines()`, so a value carrying one of these
#: passed the old `[\r\n]` validator and then vanished from the parsed table — the row
#: was absent rather than mismatched, which no comparison would ever report.
_EXTRA_SPLITLINES_CHARS = (
    "\v",
    "\f",
    "\x1c",
    "\x1d",
    "\x1e",
    "\x85",
    "\u2028",
    "\u2029",
)


@pytest.mark.parametrize("char", _EXTRA_SPLITLINES_CHARS)
def test_validate_ledger_rejects_every_character_splitlines_breaks_on(char: str) -> None:
    data = {**_VALID_LEDGER, "model_name": f"llama{char}3"}

    with pytest.raises(LedgerValidationError) as exc_info:
        validate_ledger(data)

    assert exc_info.value.field == "model_name"


@pytest.mark.parametrize("char", _EXTRA_SPLITLINES_CHARS)
def test_validate_ledger_rejects_those_characters_in_a_per_unit_metric_name(char: str) -> None:
    data = {
        **_VALID_LEDGER,
        "per_unit_metrics": [{"name": f"a{char}b", "value": 1.0, "unit": "x"}],
    }

    with pytest.raises(LedgerValidationError) as exc_info:
        validate_ledger(data)

    assert exc_info.value.field == "per_unit_metrics[0]"


@pytest.mark.parametrize("char", _EXTRA_SPLITLINES_CHARS)
def test_a_rejected_character_really_would_have_dropped_the_row(char: str) -> None:
    """Why the class had to widen, stated as an executable fact rather than a comment.

    Renders the value the validator now refuses and shows the parser losing the Model
    row entirely — the failure mode is a silently absent row, not a wrong one.
    """
    table = f"| Metric | Value |\n| --- | --- |\n| Model | llama{char}3 |\n"

    assert "Model" not in parse_ledger_markdown_table(table)


def test_validate_ledger_rejects_a_line_break_in_library_versions() -> None:
    data = {**_VALID_LEDGER, "library_versions": {"python": "3.12\n1.0"}}

    with pytest.raises(LedgerValidationError) as exc_info:
        validate_ledger(data)

    assert exc_info.value.field == "library_versions"


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


def test_validate_ledger_per_unit_metric_may_not_take_a_mandated_rows_label() -> None:
    """It would shadow that row in the rendered table instead of adding one."""
    data = {
        **_VALID_LEDGER,
        "per_unit_metrics": [{"name": "GPU active time (s)", "value": 0.01, "unit": "s"}],
    }

    with pytest.raises(LedgerValidationError) as exc_info:
        validate_ledger(data)

    assert exc_info.value.field == "per_unit_metrics[0]"
    assert "shadow" in str(exc_info.value)


def test_validate_ledger_per_unit_metric_names_must_be_unique() -> None:
    data = {
        **_VALID_LEDGER,
        "per_unit_metrics": [
            {"name": "x", "value": 1.0, "unit": "u"},
            {"name": "x", "value": 2.0, "unit": "u"},
        ],
    }

    with pytest.raises(LedgerValidationError) as exc_info:
        validate_ledger(data)

    assert exc_info.value.field == "per_unit_metrics[1]"


def test_validate_ledger_accepts_a_reason_for_a_not_applicable_field() -> None:
    data = {
        **_VALID_LEDGER,
        "not_applicable_reasons": {"cpu_active_seconds": "not measured on this run"},
    }

    ledger = validate_ledger(data)

    assert ledger.not_applicable_reasons["cpu_active_seconds"] == "not measured on this run"


def test_validate_ledger_rejects_a_reason_for_a_field_that_was_measured() -> None:
    data = {**_VALID_LEDGER, "not_applicable_reasons": {"gpu_active_seconds": "not measured"}}

    with pytest.raises(LedgerValidationError) as exc_info:
        validate_ledger(data)

    assert exc_info.value.field == "not_applicable_reasons[gpu_active_seconds]"


def test_validate_ledger_rejects_a_reason_keyed_by_an_unknown_field() -> None:
    data = {**_VALID_LEDGER, "not_applicable_reasons": {"nonsense": "because"}}

    with pytest.raises(LedgerValidationError) as exc_info:
        validate_ledger(data)

    assert exc_info.value.field == "not_applicable_reasons[nonsense]"


def test_validate_ledger_rejects_an_empty_reason() -> None:
    data = {**_VALID_LEDGER, "not_applicable_reasons": {"cpu_active_seconds": "   "}}

    with pytest.raises(LedgerValidationError) as exc_info:
        validate_ledger(data)

    assert exc_info.value.field == "not_applicable_reasons[cpu_active_seconds]"


def test_validate_ledger_reasons_not_an_object_raises() -> None:
    data = {**_VALID_LEDGER, "not_applicable_reasons": ["cpu_active_seconds"]}

    with pytest.raises(LedgerValidationError) as exc_info:
        validate_ledger(data)

    assert exc_info.value.field == "not_applicable_reasons"


def test_ledger_to_dict_round_trips_through_validate_ledger() -> None:
    ledger = validate_ledger(_VALID_LEDGER)

    rebuilt = validate_ledger(ledger_to_dict(ledger))

    assert rebuilt == ledger


def test_ledger_to_json_round_trips_through_ledger_from_json() -> None:
    data = {
        **_VALID_LEDGER,
        "not_applicable_reasons": {"cpu_active_seconds": "not measured on this run"},
    }
    ledger = validate_ledger(data)

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
