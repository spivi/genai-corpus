"""The standard cost ledger: a contract with a validator, not a docstring.

The series standardises twelve line items for every lesson:
hardware, model and precision, input and output size, assets processed, embedding or
generation calls, metered tokens, GPU and CPU active time, storage and egress,
cache-hit rate, cost per result and per 1,000, quality metric, failure rate. Several
are inherently a pair of measurements (e.g. "input and output size" needs its own
number per side), so `CostLedger` expresses the twelve items as eighteen typed fields,
one per measurement, each carrying its unit in its name (`gpu_active_seconds`, not
`gpu_time`).

Every one of those eighteen fields is *required to be explicit*: a measured value of
the field's type, or the `NOT_APPLICABLE` sentinel. A required field silently filled
with zero teaches a reader to skim the table, so the schema forbids silence, and a unit
that doesn't measure something must say so.

`NOT_APPLICABLE` has exactly two sanctioned meanings, and `not_applicable_reasons`
is what keeps them apart: *this unit has no such thing* (no GPU, no quality eval), or
*this unit did not measure it*. The second is only honest when the reason is stated,
so a reason is a validated field, keyed by line-item name, required to name a field
that really is `not_applicable`, and rendered into the published table beside the
`n/a` it explains. A silent `n/a` is therefore always the first meaning, on purpose.

`per_unit_metrics` is the escape hatch for anything unit-specific: a list of
`{name, value, unit}` rows a build can add without editing this schema at all. A unit
that adds none still validates, since the default is an empty list. A row may not take the
published label of a mandated line item, and may not repeat another row's name: both
would silently shadow a row in the rendered table rather than add one.

`validate_ledger` is the enforcement. It collects **every** problem in a raw dict
(missing fields, fields outside the schema, wrong types, unsupported schema versions,
multi-line strings that would shatter a markdown table) and raises once, listing all
of them; `.field` names the first, `.problems` carries the rest.
"""

from __future__ import annotations

import json
import re
import types
import typing
from dataclasses import asdict, dataclass, field
from typing import Any, Final, Literal, get_args, get_origin, get_type_hints

NOT_APPLICABLE: Final[str] = "not_applicable"
NotApplicable = Literal["not_applicable"]

#: The one schema shape this module implements. A ledger declaring anything else is
#: rejected rather than parsed on a guess: a version string nothing checks is a
#: comment, and this one is published inside every emitted ledger.
SCHEMA_VERSION: Final[str] = "1.0"
SUPPORTED_SCHEMA_VERSIONS: Final[frozenset[str]] = frozenset({SCHEMA_VERSION})

#: (field name, published label) for the eighteen mandated line items, in the PRD's
#: order. It lives here rather than in the serialiser because the labels are part of
#: the contract: `per_unit_metrics` rows are validated against them.
ROW_ORDER: Final[tuple[tuple[str, str], ...]] = (
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

LINE_ITEM_FIELDS: Final[tuple[str, ...]] = tuple(name for name, _ in ROW_ORDER)
RESERVED_ROW_LABELS: Final[frozenset[str]] = frozenset(label for _, label in ROW_ORDER)

_NUMBER_TYPES: Final = (int, float)
# `X | Literal[...]` resolves to `typing.Union`, not the `types.UnionType` a plain
# `X | Y` of two classes gives. Accept both, so this doesn't silently stop matching.
_UNION_ORIGINS: Final = (typing.Union, types.UnionType)
# A ledger value is one table cell. A newline does not escape in markdown; it ends the
# row, so a multi-line value silently truncates the published table rather than wrap.
#
# The class is every character `str.splitlines()` breaks on, not just `\r` and `\n`,
# because `ledger_table.parse_ledger_markdown_table` splits with `str.splitlines()`:
# a narrower validator would pass a value the parser then treats as two lines, and the
# row would vanish from the parsed table instead of failing a comparison. Verified:
# `model_name="\x85nel"` passed the old `[\r\n]` class and made the Model row
# disappear on the way back out.
# Written with escapes rather than the characters themselves: six of the ten are
# invisible in an editor, and a class you cannot see is a class nobody can review.
_LINE_BREAK = re.compile("[\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029]")
_LINE_BREAK_PROBLEM: Final = "must not contain a line break: a ledger value is one table cell"


class LedgerValidationError(ValueError):
    """A raw ledger dict failed validation.

    `.field` names the first offending field and `.problems` carries every
    `(field, problem)` pair found, so one call reports the whole set rather than
    making a caller re-run the validator once per mistake.
    """

    def __init__(
        self, field_name: str, problem: str, more: tuple[tuple[str, str], ...] = ()
    ) -> None:
        self.problems: tuple[tuple[str, str], ...] = ((field_name, problem), *more)
        self.field = field_name
        joined = "; ".join(f"field '{name}': {text}" for name, text in self.problems)
        if len(self.problems) > 1:
            joined = f"{len(self.problems)} invalid fields: {joined}"
        super().__init__(joined)


def _raise_problems(problems: list[tuple[str, str]]) -> typing.NoReturn:
    first, *rest = problems
    raise LedgerValidationError(first[0], first[1], tuple(rest))


@dataclass(frozen=True)
class PerUnitMetric:
    """One additive row a unit attaches without touching the standard schema."""

    name: str
    value: float
    unit: str


@dataclass(frozen=True)
class CostLedger:
    """Twelve mandated line items as eighteen typed fields, plus run metadata.

    Field order follows the PRD's item order; `per_unit_metrics` and
    `not_applicable_reasons` are additive, last.
    """

    unit_id: str
    schema_version: str
    measured_at: str
    library_versions: dict[str, str]

    hardware: str | NotApplicable
    model_name: str | NotApplicable
    model_precision: str | NotApplicable
    input_size_bytes: int | NotApplicable
    output_size_bytes: int | NotApplicable
    assets_processed_count: int | NotApplicable
    embedding_or_generation_calls_count: int | NotApplicable
    metered_tokens_count: int | NotApplicable
    gpu_active_seconds: float | NotApplicable
    cpu_active_seconds: float | NotApplicable
    storage_bytes: int | NotApplicable
    egress_bytes: int | NotApplicable
    cache_hit_rate: float | NotApplicable
    cost_per_result_usd: float | NotApplicable
    cost_per_1000_results_usd: float | NotApplicable
    quality_metric_name: str | NotApplicable
    quality_metric_value: float | NotApplicable
    failure_rate: float | NotApplicable

    per_unit_metrics: tuple[PerUnitMetric, ...] = ()
    not_applicable_reasons: dict[str, str] = field(default_factory=dict)


def _is_na_literal(candidate: Any) -> bool:
    return get_origin(candidate) is Literal and get_args(candidate) == (NOT_APPLICABLE,)


def _matches_type(value: Any, expected: Any) -> bool:
    """Structural check for one field's concrete (non-`NotApplicable`) type."""
    if isinstance(value, bool):
        return expected is bool
    if expected is float:
        return isinstance(value, _NUMBER_TYPES)
    if get_origin(expected) is dict:
        key_t, val_t = get_args(expected)
        return isinstance(value, dict) and all(
            isinstance(k, key_t) and isinstance(v, val_t) for k, v in value.items()
        )
    return isinstance(value, expected)


def _line_break_problem(value: Any) -> str | None:
    """`_LINE_BREAK_PROBLEM` if any string in `value` would break out of its cell."""
    if isinstance(value, str):
        texts: tuple[str, ...] = (value,)
    elif isinstance(value, dict):
        texts = tuple(k for k in value if isinstance(k, str))
        texts += tuple(v for v in value.values() if isinstance(v, str))
    else:
        return None
    return _LINE_BREAK_PROBLEM if any(_LINE_BREAK.search(t) for t in texts) else None


def _field_problem(value: Any, expected: Any) -> str | None:
    """What is wrong with one field's value, or `None` if nothing is."""
    args = get_args(expected) if get_origin(expected) in _UNION_ORIGINS else (expected,)
    na_allowed = any(_is_na_literal(a) for a in args)
    if na_allowed and value == NOT_APPLICABLE:
        return None
    concrete = [a for a in args if not _is_na_literal(a)]
    if not any(_matches_type(value, a) for a in concrete):
        wanted = " or ".join(str(a) for a in concrete)
        if na_allowed:
            wanted += f" or '{NOT_APPLICABLE}'"
        return f"wrong type: expected {wanted}, got {type(value).__name__}"
    return _line_break_problem(value)


def _core_field_hints() -> dict[str, Any]:
    hints = get_type_hints(CostLedger)
    hints.pop("per_unit_metrics", None)
    hints.pop("not_applicable_reasons", None)
    return hints


def _core_problems(data: dict[str, Any], hints: dict[str, Any]) -> list[tuple[str, str]]:
    problems = [(name, "missing required field") for name in sorted(hints.keys() - data.keys())]
    problems += [
        (name, "not part of the standard schema (use per_unit_metrics)")
        for name in sorted(data.keys() - hints.keys())
    ]
    for name, expected in hints.items():
        if name not in data:
            continue
        problem = _field_problem(data[name], expected)
        if problem is not None:
            problems.append((name, problem))
    return problems


def _schema_version_problem(data: dict[str, Any]) -> tuple[str, str] | None:
    """Reject a version this validator does not implement, rather than guessing at it."""
    version = data.get("schema_version")
    if not isinstance(version, str) or version in SUPPORTED_SCHEMA_VERSIONS:
        return None
    supported = ", ".join(sorted(SUPPORTED_SCHEMA_VERSIONS))
    problem = f"unsupported version {version!r}: this validator implements {supported}"
    return ("schema_version", problem)


_PER_UNIT_METRIC_KEYS: Final = {"name", "value", "unit"}


def _metric_shape_problem(item: Any) -> str | None:
    if not isinstance(item, dict):
        return "must be an object with name/value/unit"
    missing = _PER_UNIT_METRIC_KEYS - set(item)
    if missing:
        return f"missing key(s): {sorted(missing)}"
    extra = set(item) - _PER_UNIT_METRIC_KEYS
    if extra:
        return f"unexpected key(s): {sorted(extra)}"
    if not isinstance(item["name"], str) or not isinstance(item["unit"], str):
        return "'name' and 'unit' must be strings"
    if not isinstance(item["value"], _NUMBER_TYPES) or isinstance(item["value"], bool):
        return "'value' must be a number"
    return _line_break_problem(item["name"]) or _line_break_problem(item["unit"])


def _metric_name_problem(name: str, seen: set[str]) -> str | None:
    """Reject names that would shadow an existing table row instead of adding one."""
    if name in RESERVED_ROW_LABELS:
        return f"name {name!r} is a mandated row's published label and would shadow it"
    if name in seen:
        return f"duplicate metric name {name!r} would shadow the earlier row"
    return None


def _per_unit_metric_problems(
    items: Any,
) -> tuple[tuple[PerUnitMetric, ...], list[tuple[str, str]]]:
    if not isinstance(items, list):
        return (), [("per_unit_metrics", "must be a list")]
    metrics: list[PerUnitMetric] = []
    problems: list[tuple[str, str]] = []
    seen: set[str] = set()
    for i, item in enumerate(items):
        label = f"per_unit_metrics[{i}]"
        problem = _metric_shape_problem(item) or _metric_name_problem(item["name"], seen)
        if problem is not None:
            problems.append((label, problem))
            continue
        seen.add(item["name"])
        metrics.append(PerUnitMetric(name=item["name"], value=item["value"], unit=item["unit"]))
    return tuple(metrics), problems


def _reason_problem(name: str, reason: Any, data: dict[str, Any]) -> str | None:
    if name not in LINE_ITEM_FIELDS:
        return "not a mandated line-item field, so it cannot be not-applicable"
    if not isinstance(reason, str) or not reason.strip():
        return "must be a non-empty string explaining why the field is not applicable"
    if _LINE_BREAK.search(reason):
        return _LINE_BREAK_PROBLEM
    if name in data and data[name] != NOT_APPLICABLE:
        return f"field '{name}' carries a measured value, so it needs no reason"
    return None


def _reason_problems(
    raw: Any, data: dict[str, Any]
) -> tuple[dict[str, str], list[tuple[str, str]]]:
    if not isinstance(raw, dict):
        return {}, [("not_applicable_reasons", "must be an object of field name -> reason")]
    reasons: dict[str, str] = {}
    problems: list[tuple[str, str]] = []
    for name in sorted(raw):
        problem = _reason_problem(name, raw[name], data)
        if problem is not None:
            problems.append((f"not_applicable_reasons[{name}]", problem))
            continue
        reasons[name] = raw[name]
    return reasons, problems


def validate_ledger(data: dict[str, Any]) -> CostLedger:
    """Validate a raw ledger dict, or raise `LedgerValidationError` listing every fault.

    Checks every required field is present, no field falls outside the schema, every
    present field's type (or the `NOT_APPLICABLE` sentinel where the field allows it)
    and single-line-ness, the declared `schema_version`, the shape and uniqueness of
    `per_unit_metrics`, and that each `not_applicable_reasons` entry explains a field
    that really is not applicable. All problems are collected and raised together.
    """
    data = dict(data)
    per_unit_raw = data.pop("per_unit_metrics", [])
    reasons_raw = data.pop("not_applicable_reasons", {})
    hints = _core_field_hints()
    problems = _core_problems(data, hints)
    version_problem = _schema_version_problem(data)
    if version_problem is not None:
        problems.append(version_problem)
    metrics, metric_problems = _per_unit_metric_problems(per_unit_raw)
    reasons, reason_problems = _reason_problems(reasons_raw, data)
    problems += metric_problems + reason_problems
    if problems:
        _raise_problems(problems)
    return CostLedger(**data, per_unit_metrics=metrics, not_applicable_reasons=reasons)


def ledger_to_dict(ledger: CostLedger) -> dict[str, Any]:
    """The JSON-ready dict form, which is what a build actually emits to disk.

    `per_unit_metrics` comes back as a `list`, matching the JSON array a real ledger
    file has and the shape `validate_ledger` accepts back in, where a `tuple` would
    round-trip through Python fine but has no JSON equivalent.
    """
    payload = asdict(ledger)
    payload["per_unit_metrics"] = list(payload["per_unit_metrics"])
    return payload


def ledger_to_json(ledger: CostLedger) -> str:
    return json.dumps(ledger_to_dict(ledger), indent=2)


def ledger_from_json(text: str) -> CostLedger:
    return validate_ledger(json.loads(text))
