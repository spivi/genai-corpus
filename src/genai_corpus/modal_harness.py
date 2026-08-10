"""The Modal run-and-measure harness (SPZ-44).

Measuring is a side effect of running, not a second step an author must remember:
`run_and_measure` wraps one call and returns its result alongside the seconds and
dollars that call took, and `ledger_from_measurement` turns that straight into a
validated `CostLedger`. If either were a separate step, the ledger would eventually be
estimated instead of measured, and the series loses the one thing that distinguishes
it (M4 plan).

**What is measured is billed container time, not active compute.** The timer wraps a
`.remote()` invocation from the client side, so the span includes container cold
start, scheduling and the RPC round trip. That is the right basis for *cost* — Modal
bills a function's container for the seconds it is up — and the wrong basis for a
field named `gpu_active_seconds`. So the measurement is named for what it is,
`billed_container_seconds`, and it reaches the ledger as a `per_unit_metric` under
that name. An active-time line item is recorded as `not_applicable` *with a stated
reason* unless a caller supplies a real in-container measurement, because a number
that is ~99% cold start and RPC is not "CPU active time" by any reading. The reason
is attached only to a lane the hardware actually has: every container is billed for
CPU cores, so a bare `n/a` there would be false, while on CPU hardware a bare `n/a`
for GPU time is simply true.

Cost is `billed_container_seconds` times a pinned USD/second rate for the hardware
(`HARDWARE_RATE_USD_PER_SECOND`, sourced from https://modal.com/pricing, verified
`RATE_TABLE_VERIFIED_ON`). The rate and its vintage travel into every emitted ledger,
so a published dollar figure is re-derivable later rather than only re-assertable, and
`test_modal_harness.py` fails once the table is older than
`RATE_TABLE_MAX_AGE_DAYS` — a price is a dated fact, not a permanent one.

`weights_volume()` is the one sanctioned place later GPU units write model weights.
No function in this package writes a weight file to local disk; the repo's own
`.gitignore` refuses every weight-file extension as a second, independent guard.
"""

from __future__ import annotations

import platform
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final

import modal

from genai_corpus._version import __version__
from genai_corpus.ledger import (
    LINE_ITEM_FIELDS,
    NOT_APPLICABLE,
    SCHEMA_VERSION,
    CostLedger,
    validate_ledger,
)

APP_NAME: Final = "genai-corpus-harness"
WEIGHTS_VOLUME_NAME: Final = "genai-weights"
WEIGHTS_VOLUME_MOUNT_PATH: Final = "/vol/weights"

#: The rate-table key for a function with no `gpu=` spec.
CPU_HARDWARE: Final = "CPU"

# USD per second. Source: https://modal.com/pricing, verified RATE_TABLE_VERIFIED_ON.
# Keys are Modal's own `gpu=` spec strings, so `hardware_from_function` can derive one
# from a decorated Function rather than trusting a hand-typed label. Every GPU key
# prices one full GPU-second; a `"H100:2"`-style spec is priced at its count.
#
# "CPU" prices one *full physical core*-second. Modal bills a container for the cores
# it actually requests (minimum 0.125) plus memory GiB-seconds, so a CPU figure priced
# from this key is an upper bound unless the container asks for a whole core.
#
# Deliberately omitted: **RTX PRO 6000**, published at $0.000842/s. Its `gpu=` spec
# string was not verified, and every key in this table is one Modal itself emits so
# `hardware_from_function` can match it; a guessed key is reachable only by a
# hand-typed label, which is the failure mode this table exists to prevent. Recorded
# here so the next person does not redo the lookup and reach the opposite conclusion:
# add it when the spec string is confirmed against Modal's docs, not before.
HARDWARE_RATE_USD_PER_SECOND: Final[dict[str, float]] = {
    CPU_HARDWARE: 0.0000131,
    "T4": 0.000164,
    "L4": 0.000222,
    "A10": 0.000306,
    "L40S": 0.000542,
    "A100-40GB": 0.000583,
    "A100-80GB": 0.000694,
    "H100": 0.001097,
    "H200": 0.001261,
    "B200": 0.001736,
    "B300": 0.001972,
}

#: The day the table above was last checked against modal.com/pricing, in full.
RATE_TABLE_VERIFIED_ON: Final[date] = date(2026, 8, 10)
#: One quarter — roughly the M4 milestone's span. Past this the rate table is treated
#: as unverified and the test suite fails, rather than quietly pricing on stale data.
RATE_TABLE_MAX_AGE_DAYS: Final[int] = 90

app = modal.App(APP_NAME)


class HardwareMismatchError(ValueError):
    """A named `hardware` disagrees with the Modal Function's own `gpu=` spec."""


@dataclass(frozen=True)
class RunMeasurement[T]:
    """One call's result, plus what it measurably cost to produce.

    `billed_container_seconds` is wall-clock around the invocation — the span Modal
    bills, cold start and RPC included. It is deliberately *not* called GPU or CPU
    active time; see this module's docstring.
    """

    result: T
    hardware: str
    billed_container_seconds: float
    rate_usd_per_second: float
    cost_usd: float


def rate_table_age_days(today: date | None = None) -> int:
    """Days since the rate table was last verified against Modal's published prices."""
    return ((today or date.today()) - RATE_TABLE_VERIFIED_ON).days


def resolve_hardware_rate(hardware: str) -> float:
    """USD/second for a hardware spec, honouring a `"H100:2"`-style GPU count.

    Raises rather than defaulting: an unknown key priced at zero would publish a run
    as free, which is the one failure mode a cost ledger must not have.

    The branch is on the *separator*, not on the count text. Keying off `count_text`
    made `"H100:"` fall through to the single-GPU rate — an empty string is falsy —
    while `"H100:0"`, `"H100:-2"` and `"H100:many"` were all correctly rejected. A
    malformed spec is malformed whether or not it happens to be empty.
    """
    key, separator, count_text = hardware.partition(":")
    if key not in HARDWARE_RATE_USD_PER_SECOND:
        raise ValueError(f"unknown hardware '{hardware}': add its rate before using it")
    count = 1
    if separator:
        if not count_text.isdigit() or int(count_text) < 1:
            raise ValueError(f"bad GPU count in hardware '{hardware}': expected '<name>:<n>'")
        count = int(count_text)
    return count * HARDWARE_RATE_USD_PER_SECOND[key]


def hardware_from_function(function: modal.Function) -> str:
    """The rate-table key implied by a Modal Function's own `gpu=` spec.

    Deriving beats declaring: a function decorated `gpu="H100"` and measured against a
    hand-typed `"T4"` would price at ~15% of its true cost, and nothing else in this
    package would notice.
    """
    spec = getattr(function, "spec", None)
    if spec is None or not hasattr(spec, "gpus"):
        raise HardwareMismatchError(
            "this modal version does not expose Function.spec.gpus; name hardware explicitly"
        )
    gpus = spec.gpus
    if gpus is None:
        return CPU_HARDWARE
    if not isinstance(gpus, str):
        raise HardwareMismatchError(
            f"heterogeneous gpu spec {gpus!r} has no single rate; name hardware explicitly"
        )
    return gpus


def run_and_measure[T](
    call: Callable[[], T], hardware: str, function: modal.Function | None = None
) -> RunMeasurement[T]:
    """Run `call` once and return its result with the seconds/dollars it took.

    `call` is a zero-argument closure — typically `lambda: some_fn.remote(x, y)` — so
    the timer wraps exactly the remote invocation. Pass `function=some_fn` to have the
    named `hardware` checked against that function's own `gpu=` spec; a disagreement
    raises `HardwareMismatchError` before the call runs. An unrecognized `hardware`
    raises too, rather than silently pricing the run at zero.
    """
    rate = resolve_hardware_rate(hardware)
    if function is not None:
        declared = hardware_from_function(function)
        if declared != hardware:
            raise HardwareMismatchError(
                f"hardware '{hardware}' but the function's gpu spec is '{declared}'"
            )
    started = time.perf_counter()
    result = call()
    elapsed = time.perf_counter() - started
    return RunMeasurement(
        result=result,
        hardware=hardware,
        billed_container_seconds=elapsed,
        rate_usd_per_second=rate,
        cost_usd=elapsed * rate,
    )


def capture_library_versions(extra: dict[str, str] | None = None) -> dict[str, str]:
    """The interpreter/package versions this run used — a ledger field, not a comment.

    `extra` records the libraries a *unit* depends on, which this package cannot know:
    the M4 plan's Risk 4 is about bitsandbytes' 8-bit optimizers and the MPS backend,
    so a QLoRA unit passes `{"torch": ..., "bitsandbytes": ...}` here rather than
    hand-merging keys into the ledger afterwards. Shadowing a base key is refused —
    a version this harness measured must not be overwritten with a claimed one.
    """
    versions = {
        "python": platform.python_version(),
        "modal": modal.__version__,
        "genai_corpus": __version__,
    }
    clash = sorted(set(extra or {}) & set(versions))
    if clash:
        raise ValueError(f"extra library versions may not shadow measured keys: {clash}")
    versions.update(extra or {})
    return versions


_ACTIVE_TIME_REASON: Final = (
    "not measured: this harness times the billed container span (cold start, scheduling "
    "and RPC included), which is the cost basis but not in-container active compute"
)


def _unmeasured_active_time_reasons(hardware: str, payload: dict[str, Any]) -> dict[str, str]:
    """Reasons for the active-time lanes this hardware *has* but this harness misses.

    Every Modal container runs on CPU cores and is billed for them, so a CPU lane
    always exists and a bare `n/a` there would be false. A GPU lane exists only on GPU
    hardware, where a bare `n/a` correctly reads as "this unit has no GPU".
    """
    lanes = ["cpu_active_seconds"]
    if hardware != CPU_HARDWARE:
        lanes.append("gpu_active_seconds")
    return {name: _ACTIVE_TIME_REASON for name in lanes if payload[name] == NOT_APPLICABLE}


def _measurement_metrics(measurement: RunMeasurement[Any]) -> list[dict[str, Any]]:
    """The cost provenance every emitted ledger carries, so a figure is re-derivable."""
    return [
        {
            "name": "billed_container_seconds",
            "value": measurement.billed_container_seconds,
            "unit": "s",
        },
        {
            "name": "hardware_rate_usd_per_second",
            "value": measurement.rate_usd_per_second,
            "unit": f"USD/s (modal.com/pricing, verified {RATE_TABLE_VERIFIED_ON.isoformat()})",
        },
    ]


def ledger_from_measurement(
    measurement: RunMeasurement[Any], unit_id: str, results: int = 1, **fields: Any
) -> CostLedger:
    """Build a validated `CostLedger` from a measurement — the seam, not a hand-copy.

    Fills the run metadata, the hardware, the cost line items (from `results`, the
    number of results the run produced) and the two active-time items, and attaches
    the billed seconds and the rate that priced them as `per_unit_metrics`. Any line
    item you pass in `fields` wins, including `per_unit_metrics` rows, which are
    appended to the provenance rows rather than replacing them.

    `hardware` is the one line item `fields` may not disagree with. It is what priced
    the run, and it also decides which active-time lane gets a stated reason, so a
    ledger whose hardware and rate came from different machines would misdescribe both
    its cost and its GPU lane — silently, and in the published table.

    A line item you do not pass is recorded as a silent `not_applicable`, which this
    schema reads as *this unit has no such thing*. If your unit **has** one but did not
    measure it, say so: pass `not_applicable_reasons={"field": "why"}`.
    """
    if results < 1:
        raise ValueError(f"results must be at least 1, got {results}")
    if fields.get("hardware", measurement.hardware) != measurement.hardware:
        raise ValueError(
            f"hardware '{fields['hardware']}' contradicts the measurement's "
            f"'{measurement.hardware}', which is what priced this run"
        )
    caller_reasons = dict(fields.pop("not_applicable_reasons", {}))
    caller_metrics = list(fields.pop("per_unit_metrics", []))
    cost_per_result = measurement.cost_usd / results
    payload: dict[str, Any] = dict.fromkeys(LINE_ITEM_FIELDS, NOT_APPLICABLE)
    payload.update(
        unit_id=unit_id,
        schema_version=SCHEMA_VERSION,
        measured_at=datetime.now(UTC).isoformat(),
        library_versions=capture_library_versions(),
        hardware=measurement.hardware,
        cost_per_result_usd=cost_per_result,
        cost_per_1000_results_usd=cost_per_result * 1000,
    )
    payload.update(fields)
    reasons = _unmeasured_active_time_reasons(payload["hardware"], payload)
    reasons.update(caller_reasons)
    payload["not_applicable_reasons"] = reasons
    payload["per_unit_metrics"] = _measurement_metrics(measurement) + caller_metrics
    return validate_ledger(payload)


def weights_volume() -> modal.Volume:
    """The persistent volume GPU units mount for model weights.

    A function that downloads or trains weights mounts this at
    `WEIGHTS_VOLUME_MOUNT_PATH` and writes there. Nothing in this package, and no
    later unit following this layout, writes a weight file to local disk instead.
    """
    return modal.Volume.from_name(WEIGHTS_VOLUME_NAME, create_if_missing=True)


@app.function()
def cpu_probe(n: int) -> int:
    """A trivial CPU function this package's one mandated hand-run exercises.

    Not part of the public API (not exported from `__init__.py`): it exists only so
    `scripts/hand_run_spz44.py` has something real to run on Modal, proving the
    harness round-trips through the live service rather than only through mocks.
    """
    return sum(range(n))
