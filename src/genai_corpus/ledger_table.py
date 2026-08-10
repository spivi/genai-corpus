"""Serialises a validated `CostLedger` into the article's published table (SPZ-44).

This is what makes "generated, never hand-typed" true rather than aspirational: an
article's cost table is `render_ledger_markdown_table`'s output, verbatim. Risk 8 in
the M4 plan names ledger drift between article and repo as a threat to the reader —
generation from one schema, with a round-trip test proving it, is the mitigation.
"""

from __future__ import annotations

from genai_corpus.ledger import NOT_APPLICABLE, CostLedger

# (field name, published label) — order follows the PRD's twelve mandated items.
_ROW_ORDER: tuple[tuple[str, str], ...] = (
    ("hardware", "Hardware"),
    ("model_name", "Model"),
    ("model_precision", "Precision"),
    ("input_size_bytes", "Input size (bytes)"),
    ("output_size_bytes", "Output size (bytes)"),
    ("assets_processed_count", "Assets processed (count)"),
    ("embedding_or_generation_calls_count", "Embedding/generation calls (count)"),
    ("metered_tokens_count", "Metered tokens (count)"),
    ("gpu_active_seconds", "GPU active time (s)"),
    ("cpu_active_seconds", "CPU active time (s)"),
    ("storage_bytes", "Storage (bytes)"),
    ("egress_bytes", "Egress (bytes)"),
    ("cache_hit_rate", "Cache-hit rate"),
    ("cost_per_result_usd", "Cost per result (USD)"),
    ("cost_per_1000_results_usd", "Cost per 1,000 results (USD)"),
    ("quality_metric_name", "Quality metric"),
    ("quality_metric_value", "Quality metric value"),
    ("failure_rate", "Failure rate"),
)

_HEADER = ("| Metric | Value |", "| --- | --- |")


def _format_value(value: object) -> str:
    """`n/a` for the not-applicable sentinel; the plain string form otherwise."""
    if value == NOT_APPLICABLE:
        return "n/a"
    return str(value)


def render_ledger_markdown_table(ledger: CostLedger) -> str:
    """The two-column `Metric | Value` markdown table for `ledger`'s article.

    Row order follows the twelve mandated line items; any `per_unit_metrics` the unit
    attached are appended after them, unmodified.
    """
    lines = list(_HEADER)
    for field_name, label in _ROW_ORDER:
        lines.append(f"| {label} | {_format_value(getattr(ledger, field_name))} |")
    for metric in ledger.per_unit_metrics:
        lines.append(f"| {metric.name} | {metric.value} {metric.unit} |")
    return "\n".join(lines)


def parse_ledger_markdown_table(table: str) -> dict[str, str]:
    """Parse a table `render_ledger_markdown_table` produced back into label -> value.

    Exists so a round-trip test can prove the table it reads back says exactly what
    the ledger it was built from says, not just that the renderer ran without error.
    """
    rows: dict[str, str] = {}
    for line in table.splitlines()[len(_HEADER) :]:
        if not line.startswith("|"):
            continue
        label, _, value = line.strip("|").partition("|")
        rows[label.strip()] = value.strip()
    return rows
