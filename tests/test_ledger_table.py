from __future__ import annotations

from genai_corpus.ledger import NOT_APPLICABLE, validate_ledger
from genai_corpus.ledger_table import (
    _ROW_ORDER,
    _format_value,
    parse_ledger_markdown_table,
    render_ledger_markdown_table,
)

_LEDGER_DATA = {
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
    "per_unit_metrics": [{"name": "tokens_per_dollar", "value": 500.0, "unit": "tokens/usd"}],
}


def test_render_ledger_markdown_table_includes_every_mandated_row() -> None:
    ledger = validate_ledger(_LEDGER_DATA)

    table = render_ledger_markdown_table(ledger)

    for _, label in _ROW_ORDER:
        assert f"| {label} |" in table


def test_render_ledger_markdown_table_renders_not_applicable_as_na() -> None:
    ledger = validate_ledger(_LEDGER_DATA)

    table = render_ledger_markdown_table(ledger)

    assert "| Metered tokens (count) | n/a |" in table
    assert "| Quality metric | n/a |" in table


def test_render_ledger_markdown_table_appends_per_unit_metric_rows() -> None:
    ledger = validate_ledger(_LEDGER_DATA)

    table = render_ledger_markdown_table(ledger)

    assert "| tokens_per_dollar | 500.0 tokens/usd |" in table


def test_render_and_parse_round_trips_every_field_in_the_ledger() -> None:
    """The acceptance-mandated round-trip: the table's numbers equal the ledger's."""
    ledger = validate_ledger(_LEDGER_DATA)

    table = render_ledger_markdown_table(ledger)
    parsed = parse_ledger_markdown_table(table)

    for field_name, label in _ROW_ORDER:
        assert parsed[label] == _format_value(getattr(ledger, field_name))


def test_render_and_parse_round_trips_per_unit_metric_rows() -> None:
    ledger = validate_ledger(_LEDGER_DATA)

    parsed = parse_ledger_markdown_table(render_ledger_markdown_table(ledger))

    metric = ledger.per_unit_metrics[0]
    assert parsed[metric.name] == f"{metric.value} {metric.unit}"


def test_parse_ledger_markdown_table_ignores_non_table_lines() -> None:
    table = "| Metric | Value |\n| --- | --- |\n| Hardware | A10G |\n\nnot a table row"

    parsed = parse_ledger_markdown_table(table)

    assert parsed == {"Hardware": "A10G"}
