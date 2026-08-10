"""The standard cost ledger (SPZ-44): a contract with a validator, not a docstring.

`M4-generative-ai-engineering.md` mandates twelve line items for every lesson:
hardware, model and precision, input and output size, assets processed, embedding or
generation calls, metered tokens, GPU and CPU active time, storage and egress,
cache-hit rate, cost per result and per 1,000, quality metric, failure rate. Several
are inherently a pair of measurements (e.g. "input and output size" needs its own
number per side) — `CostLedger` expresses the twelve items as eighteen typed fields,
one per measurement, each carrying its unit in its name (`gpu_active_seconds`, not
`gpu_time`).

Every one of those eighteen fields is *required to be explicit*: a measured value of
the field's type, or the `NOT_APPLICABLE` sentinel. A required field silently filled
with zero teaches a reader to skim the table, so the schema forbids silence — a unit
that doesn't measure something must say so.

`per_unit_metrics` is the escape hatch for anything unit-specific: a list of
`{name, value, unit}` rows a build can add without editing this schema at all. A unit
that adds none still validates — the default is an empty list.

`validate_ledger` is the enforcement: a raw dict missing a field, carrying a field of
the wrong type, or inventing a field outside the schema raises `LedgerValidationError`
naming exactly which field is wrong.
"""

from __future__ import annotations

import json
import types
import typing
from dataclasses import asdict, dataclass
from typing import Any, Final, Literal, get_args, get_origin, get_type_hints

NOT_APPLICABLE: Final[str] = "not_applicable"
NotApplicable = Literal["not_applicable"]

_NUMBER_TYPES: Final = (int, float)
# `X | Literal[...]` resolves to `typing.Union`, not the `types.UnionType` a plain
# `X | Y` of two classes gives — accept both so this doesn't silently stop matching.
_UNION_ORIGINS: Final = (typing.Union, types.UnionType)


class LedgerValidationError(ValueError):
    """A raw ledger dict failed validation. `.field` names exactly which one."""

    def __init__(self, field: str, problem: str) -> None:
        self.field = field
        super().__init__(f"field '{field}': {problem}")


@dataclass(frozen=True)
class PerUnitMetric:
    """One additive row a unit attaches without touching the standard schema."""

    name: str
    value: float
    unit: str


@dataclass(frozen=True)
class CostLedger:
    """Twelve mandated line items as eighteen typed fields, plus run metadata.

    Field order follows the PRD's item order; `per_unit_metrics` is additive, last.
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


def _check_field(name: str, value: Any, expected: Any) -> None:
    args = get_args(expected) if get_origin(expected) in _UNION_ORIGINS else (expected,)
    na_allowed = any(_is_na_literal(a) for a in args)
    if na_allowed and value == NOT_APPLICABLE:
        return
    concrete = [a for a in args if not _is_na_literal(a)]
    if any(_matches_type(value, a) for a in concrete):
        return
    wanted = " or ".join(str(a) for a in concrete)
    if na_allowed:
        wanted += f" or '{NOT_APPLICABLE}'"
    got = type(value).__name__
    raise LedgerValidationError(name, f"wrong type: expected {wanted}, got {got}")


def _core_field_hints() -> dict[str, Any]:
    hints = get_type_hints(CostLedger)
    hints.pop("per_unit_metrics", None)
    return hints


_PER_UNIT_METRIC_KEYS: Final = {"name", "value", "unit"}


def _validate_per_unit_metrics(items: Any) -> tuple[PerUnitMetric, ...]:
    if not isinstance(items, list):
        raise LedgerValidationError("per_unit_metrics", "must be a list")
    metrics: list[PerUnitMetric] = []
    for i, item in enumerate(items):
        label = f"per_unit_metrics[{i}]"
        if not isinstance(item, dict):
            raise LedgerValidationError(label, "must be an object with name/value/unit")
        missing = _PER_UNIT_METRIC_KEYS - set(item)
        extra = set(item) - _PER_UNIT_METRIC_KEYS
        if missing:
            raise LedgerValidationError(label, f"missing key(s): {sorted(missing)}")
        if extra:
            raise LedgerValidationError(label, f"unexpected key(s): {sorted(extra)}")
        if not isinstance(item["name"], str) or not isinstance(item["unit"], str):
            raise LedgerValidationError(label, "'name' and 'unit' must be strings")
        if not isinstance(item["value"], _NUMBER_TYPES) or isinstance(item["value"], bool):
            raise LedgerValidationError(label, "'value' must be a number")
        metrics.append(PerUnitMetric(name=item["name"], value=item["value"], unit=item["unit"]))
    return tuple(metrics)


def validate_ledger(data: dict[str, Any]) -> CostLedger:
    """Validate a raw ledger dict, or raise `LedgerValidationError` naming the field.

    Checks, in order: every required field present, no field outside the schema,
    every present field's type (or the `NOT_APPLICABLE` sentinel where the field
    allows it), then `per_unit_metrics` shape.
    """
    data = dict(data)
    per_unit_raw = data.pop("per_unit_metrics", [])
    hints = _core_field_hints()
    missing = hints.keys() - data.keys()
    if missing:
        raise LedgerValidationError(sorted(missing)[0], "missing required field")
    extra = data.keys() - hints.keys()
    if extra:
        raise LedgerValidationError(
            sorted(extra)[0], "not part of the standard schema (use per_unit_metrics)"
        )
    for name, expected in hints.items():
        _check_field(name, data[name], expected)
    metrics = _validate_per_unit_metrics(per_unit_raw)
    return CostLedger(**data, per_unit_metrics=metrics)


def ledger_to_dict(ledger: CostLedger) -> dict[str, Any]:
    """The JSON-ready dict form — what a build actually emits to disk.

    `per_unit_metrics` comes back as a `list`, matching the JSON array a real ledger
    file has and the shape `validate_ledger` accepts back in — a `tuple` would
    round-trip through Python fine but has no JSON equivalent.
    """
    payload = asdict(ledger)
    payload["per_unit_metrics"] = list(payload["per_unit_metrics"])
    return payload


def ledger_to_json(ledger: CostLedger) -> str:
    return json.dumps(ledger_to_dict(ledger), indent=2)


def ledger_from_json(text: str) -> CostLedger:
    return validate_ledger(json.loads(text))
