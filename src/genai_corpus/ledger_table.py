"""Serialises a validated `CostLedger` into the article's published table.

This is what makes "generated, never hand-typed" true rather than aspirational: an
article's cost table is `render_ledger_markdown_table`'s output, verbatim. Ledger
drift between the article and the repo is a threat to the reader, and generation from
one schema, with a round-trip test proving it, is what removes it.

Two properties this module owes a public article. Cell values are **escaped**: a
`|` inside a model name or unit would otherwise open a third column against a
two-column header, so it is written `\\|` here and unescaped by the parser. No line
break reaches this point either, and the two modules have to agree on what one *is*:
the parser below splits with `str.splitlines()`, so `validate_ledger` rejects every
character `str.splitlines()` breaks on: `\\v`, `\\f`, `\\x1c`, `\\x1d`, `\\x1e`,
`\\x85`, `U+2028` and `U+2029` as well as `\\r` and `\\n`. A narrower validator would
let a value through that the parser then reads as two lines, dropping the row from the
parsed table instead of failing a comparison.

And an `n/a` that carries a `not_applicable_reasons` entry is published *with* its
reason, so a reader sees the difference between "this unit has no GPU" and "this run
did not measure it".
"""

from __future__ import annotations

from genai_corpus.ledger import NOT_APPLICABLE, ROW_ORDER, CostLedger

_HEADER = ("| Metric | Value |", "| --- | --- |")
_NA_TEXT = "n/a"
_REASON_SEPARATOR = ", "


def _escape_cell(text: str) -> str:
    """Make `text` safe to sit inside one markdown cell."""
    return text.replace("\\", "\\\\").replace("|", "\\|")


def _unescape_cell(text: str) -> str:
    """The inverse of `_escape_cell`, so a parsed cell equals the value rendered."""
    out: list[str] = []
    escaped = False
    for char in text:
        if escaped:
            out.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        else:
            out.append(char)
    return "".join(out)


def _format_value(value: object, reason: str | None = None) -> str:
    """`n/a` (with its stated reason, if any) for the sentinel; the escaped form else."""
    if value == NOT_APPLICABLE:
        rendered = _NA_TEXT if reason is None else f"{_NA_TEXT}{_REASON_SEPARATOR}{reason}"
    else:
        rendered = str(value)
    return _escape_cell(rendered)


def render_ledger_markdown_table(ledger: CostLedger) -> str:
    """The two-column `Metric | Value` markdown table for `ledger`'s article.

    Row order follows the twelve mandated line items; any `per_unit_metrics` the unit
    attached are appended after them, unmodified.
    """
    lines = list(_HEADER)
    for field_name, label in ROW_ORDER:
        value = _format_value(
            getattr(ledger, field_name), ledger.not_applicable_reasons.get(field_name)
        )
        lines.append(f"| {_escape_cell(label)} | {value} |")
    for metric in ledger.per_unit_metrics:
        # Through `_format_value`, not around it. These rows carry
        # `billed_container_seconds` and `hardware_rate_usd_per_second`, the two
        # numbers a published cost is derived from, so they need the same formatter
        # the round-trip test proves is lossless, not a private one it never sees.
        value = f"{_format_value(metric.value)} {_escape_cell(metric.unit)}"
        lines.append(f"| {_escape_cell(metric.name)} | {value} |")
    return "\n".join(lines)


def _split_row(line: str) -> list[str]:
    """Split a table row on its unescaped pipes only."""
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            current.append(char)
            escaped = True
        elif char == "|":
            cells.append("".join(current))
            current = []
        else:
            current.append(char)
    cells.append("".join(current))
    return cells


def parse_ledger_markdown_table(table: str) -> dict[str, str]:
    """Parse a table `render_ledger_markdown_table` produced back into label -> value.

    Exists so a round-trip test can prove the table it reads back says exactly what
    the ledger it was built from says, not just that the renderer ran without error.
    Escaping is undone, so a parsed cell equals the string that was rendered into it.
    """
    rows: dict[str, str] = {}
    for line in table.splitlines()[len(_HEADER) :]:
        if not line.startswith("|"):
            continue
        cells = _split_row(line.strip())
        if len(cells) < 4:
            continue
        rows[_unescape_cell(cells[1]).strip()] = _unescape_cell(cells[2]).strip()
    return rows
