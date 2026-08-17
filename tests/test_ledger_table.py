from __future__ import annotations

from typing import Any

import pytest

from genai_corpus import ledger_table
from genai_corpus.ledger import (
    NOT_APPLICABLE,
    ROW_ORDER,
    SCHEMA_VERSION,
    CostLedger,
    validate_ledger,
)
from genai_corpus.ledger_table import (
    parse_ledger_markdown_table,
    render_ledger_markdown_table,
)

_LEDGER_DATA: dict[str, Any] = {
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
    "cost_per_result_usd": 4.647473081252537e-05,
    "cost_per_1000_results_usd": 0.04647473081252537,
    "quality_metric_name": NOT_APPLICABLE,
    "quality_metric_value": NOT_APPLICABLE,
    "failure_rate": 0.0,
    # Deliberately not a round number: a fixture of `500.0` survives any rounding a
    # lossy formatter could apply, so it would prove nothing about the metric rows.
    "per_unit_metrics": [
        {"name": "tokens_per_dollar", "value": 3.4246967090293765, "unit": "tokens/usd"}
    ],
    "not_applicable_reasons": {"cpu_active_seconds": "not measured: billed span only"},
}

#: Every mandated float here survives rounding to one decimal, so the only row a lossy
#: formatter can damage is the per-unit metric. That makes it the fixture that proves
#: the per-unit-metric arm of the round-trip check does the catching, rather than a
#: mandated row failing first and hiding a gap behind it.
_ROUND_MANDATED_FLOATS: dict[str, Any] = {
    **_LEDGER_DATA,
    "cost_per_result_usd": 0.5,
    "cost_per_1000_results_usd": 500.0,
    "per_unit_metrics": [
        {"name": "billed_container_seconds", "value": 3.4246967090293765, "unit": "s"}
    ],
}


def _assert_metric_rows_equal_the_ledgers(ledger: CostLedger, parsed: dict[str, str]) -> None:
    """The same non-circular check, extended to `per_unit_metrics`.

    Not decoration: a review fix moved `billed_container_seconds` and
    `hardware_rate_usd_per_second`, the two numbers every published cost is derived
    from, out of `ROW_ORDER` and into these rows. A renderer that rounded them to one
    decimal would publish a rate of `0.0`, i.e. a free run, while every mandated row
    still round-tripped. The cell is `"<value> <unit>"` and a unit may itself contain
    spaces, so only the first space separates them.
    """
    for metric in ledger.per_unit_metrics:
        value_text, _, unit_text = parsed[metric.name].partition(" ")
        assert float(value_text) == metric.value, f"{metric.name}: value did not round-trip"
        assert unit_text == metric.unit, f"{metric.name}: unit did not round-trip"


def _assert_table_numbers_equal_the_ledgers(ledger: CostLedger) -> None:
    """The acceptance criterion, checked against typed values rather than strings.

    Comparing a cell to `_format_value(...)` would only prove the renderer agrees with
    itself; a formatter that rounded 3.547689375001937 to "3.5" would still pass. So
    numeric cells are parsed back with `int`/`float` and compared to the ledger's own
    value, and an `n/a` cell must carry the reason the ledger states.
    """
    parsed = parse_ledger_markdown_table(render_ledger_markdown_table(ledger))
    _assert_metric_rows_equal_the_ledgers(ledger, parsed)

    for field_name, label in ROW_ORDER:
        value = getattr(ledger, field_name)
        cell = parsed[label]
        reason = ledger.not_applicable_reasons.get(field_name)
        if value == NOT_APPLICABLE:
            assert cell == ("n/a" if reason is None else f"n/a, {reason}")
        elif isinstance(value, bool):
            raise AssertionError(f"{field_name}: bool is not a ledger value type")
        elif isinstance(value, int):
            assert int(cell) == value
        elif isinstance(value, float):
            assert float(cell) == value
        else:
            assert cell == value


def test_render_ledger_markdown_table_includes_every_mandated_row() -> None:
    ledger = validate_ledger(_LEDGER_DATA)

    table = render_ledger_markdown_table(ledger)

    for _, label in ROW_ORDER:
        assert f"| {label} |" in table


def test_render_ledger_markdown_table_renders_not_applicable_as_na() -> None:
    ledger = validate_ledger(_LEDGER_DATA)

    table = render_ledger_markdown_table(ledger)

    assert "| Metered tokens (count) | n/a |" in table
    assert "| Quality metric | n/a |" in table


def test_render_ledger_markdown_table_publishes_the_reason_beside_the_na() -> None:
    """A silent `n/a` means "no such thing"; a stated one means "not measured"."""
    ledger = validate_ledger(_LEDGER_DATA)

    table = render_ledger_markdown_table(ledger)

    assert "| CPU active time (s) | n/a, not measured: billed span only |" in table


def test_render_ledger_markdown_table_appends_per_unit_metric_rows() -> None:
    ledger = validate_ledger(_LEDGER_DATA)

    table = render_ledger_markdown_table(ledger)

    assert "| tokens_per_dollar | 3.4246967090293765 tokens/usd |" in table


def test_render_and_parse_round_trips_every_field_in_the_ledger() -> None:
    _assert_table_numbers_equal_the_ledgers(validate_ledger(_LEDGER_DATA))


def test_the_round_trip_check_catches_a_lossy_formatter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proof the check above is not circular: rounding in the renderer must fail it."""

    original = ledger_table._format_value

    def lossy(value: object, reason: str | None = None) -> str:
        if isinstance(value, float):
            return str(round(value, 1))
        return original(value, reason)

    monkeypatch.setattr(ledger_table, "_format_value", lossy)

    with pytest.raises(AssertionError):
        _assert_table_numbers_equal_the_ledgers(validate_ledger(_LEDGER_DATA))


def test_the_round_trip_check_catches_a_lossy_formatter_on_a_per_unit_metric_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same proof, isolated to the rows the fix made load-bearing.

    The test above would pass even if the check skipped `per_unit_metrics` entirely, since
    a mandated float fails first. Here every mandated float is round, so an
    `AssertionError` can only come from the metric row: `billed_container_seconds`
    rendered as `3.4` rather than `3.4246967090293765`.
    """

    original = ledger_table._format_value

    def lossy(value: object, reason: str | None = None) -> str:
        if isinstance(value, float):
            return str(round(value, 1))
        return original(value, reason)

    monkeypatch.setattr(ledger_table, "_format_value", lossy)

    ledger = validate_ledger(_ROUND_MANDATED_FLOATS)
    # Guard the guard: if a mandated row were lossy too, this test would pass for the
    # wrong reason, so prove the mandated rows survive the same formatter untouched.
    parsed = parse_ledger_markdown_table(render_ledger_markdown_table(ledger))
    for field_name, label in ROW_ORDER:
        value = getattr(ledger, field_name)
        if isinstance(value, float) and not isinstance(value, bool):
            assert float(parsed[label]) == value, f"{field_name} was damaged, not the metric row"

    with pytest.raises(AssertionError, match="billed_container_seconds"):
        _assert_table_numbers_equal_the_ledgers(ledger)


def test_round_trip_survives_a_pipe_in_an_author_supplied_value() -> None:
    """`model_name='llama|3'` must not open a third column against a two-column head."""
    ledger = validate_ledger({**_LEDGER_DATA, "model_name": "llama|3", "hardware": "A10|x"})

    table = render_ledger_markdown_table(ledger)

    for line in table.splitlines():
        assert line.count("|") - line.count("\\|") == 3
    _assert_table_numbers_equal_the_ledgers(ledger)


def test_round_trip_survives_a_pipe_in_a_per_unit_metric_name_or_unit() -> None:
    ledger = validate_ledger(
        {
            **_LEDGER_DATA,
            "per_unit_metrics": [{"name": "a|b", "value": 1.0, "unit": "x|y"}],
        }
    )

    parsed = parse_ledger_markdown_table(render_ledger_markdown_table(ledger))

    assert parsed["a|b"] == "1.0 x|y"


def test_render_and_parse_round_trips_per_unit_metric_rows() -> None:
    ledger = validate_ledger(_LEDGER_DATA)

    parsed = parse_ledger_markdown_table(render_ledger_markdown_table(ledger))

    metric = ledger.per_unit_metrics[0]
    assert parsed[metric.name] == f"{metric.value} {metric.unit}"


def test_parse_ledger_markdown_table_ignores_non_table_lines() -> None:
    table = "| Metric | Value |\n| --- | --- |\n| Hardware | A10 |\n\nnot a table row"

    parsed = parse_ledger_markdown_table(table)

    assert parsed == {"Hardware": "A10"}
