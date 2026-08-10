"""The Modal run-and-measure harness (SPZ-44).

Measuring is a side effect of running, not a second step an author must remember:
`run_and_measure` wraps one call and returns its result alongside the GPU seconds, CPU
seconds and dollar cost that call took — one call in, one measurement out. If
measuring were a separate step, the ledger would eventually be estimated instead of
measured, and the series loses the one thing that distinguishes it (M4 plan).

Cost is measured wall-clock seconds around the call, times a pinned USD/second rate
for the requested `hardware` (`HARDWARE_RATE_USD_PER_SECOND`, sourced from
https://modal.com/pricing, verified 2026-08-10). Modal bills a function's container
for the seconds it is up; wall time around a single-shot `.remote()` call is exactly
that duration. Re-verify the rate table at each unit's kickoff, the same discipline
the M4 plan's Risk 4 applies to pinned package versions — a price is a dated fact,
not a permanent one.

`weights_volume()` is the one sanctioned place later GPU units write model weights.
No function in this package writes a weight file to local disk; the repo's own
`.gitignore` refuses every weight-file extension as a second, independent guard.
"""

from __future__ import annotations

import platform
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Generic, TypeVar

import modal

from genai_corpus._version import __version__
from genai_corpus.ledger import NOT_APPLICABLE, NotApplicable

APP_NAME: Final = "genai-corpus-harness"
WEIGHTS_VOLUME_NAME: Final = "genai-weights"
WEIGHTS_VOLUME_MOUNT_PATH: Final = "/vol/weights"

# USD per second. Source: https://modal.com/pricing, verified 2026-08-10. "CPU" is
# priced per physical core-second; every GPU key prices one full GPU-second.
HARDWARE_RATE_USD_PER_SECOND: Final[dict[str, float]] = {
    "CPU": 0.0000131,
    "T4": 0.000164,
    "L4": 0.000222,
    "A10G": 0.000306,
    "L40S": 0.000542,
    "A100-40GB": 0.000583,
    "A100-80GB": 0.000694,
    "H100": 0.001097,
    "H200": 0.001261,
    "B200": 0.001736,
    "B300": 0.001972,
}

app = modal.App(APP_NAME)

T = TypeVar("T")


@dataclass(frozen=True)
class RunMeasurement(Generic[T]):
    """One call's result, plus what it measurably cost to produce."""

    result: T
    hardware: str
    gpu_active_seconds: float | NotApplicable
    cpu_active_seconds: float | NotApplicable
    cost_usd: float


def weights_volume() -> modal.Volume:
    """The persistent volume GPU units mount for model weights.

    A function that downloads or trains weights mounts this at
    `WEIGHTS_VOLUME_MOUNT_PATH` and writes there. Nothing in this package, and no
    later unit following this layout, writes a weight file to local disk instead.
    """
    return modal.Volume.from_name(WEIGHTS_VOLUME_NAME, create_if_missing=True)


def run_and_measure(call: Callable[[], T], hardware: str) -> RunMeasurement[T]:
    """Run `call` once and return its result with the seconds/dollars it took.

    `call` is a zero-argument closure — typically `lambda: some_fn.remote(x, y)` — so
    the timer wraps exactly the remote invocation. An unrecognized `hardware` raises
    before `call` ever runs, rather than silently pricing the run at zero.
    """
    if hardware not in HARDWARE_RATE_USD_PER_SECOND:
        raise ValueError(f"unknown hardware '{hardware}': add its rate before using it")
    started = time.perf_counter()
    result = call()
    elapsed = time.perf_counter() - started
    is_gpu = hardware != "CPU"
    return RunMeasurement(
        result=result,
        hardware=hardware,
        gpu_active_seconds=elapsed if is_gpu else NOT_APPLICABLE,
        cpu_active_seconds=elapsed if not is_gpu else NOT_APPLICABLE,
        cost_usd=elapsed * HARDWARE_RATE_USD_PER_SECOND[hardware],
    )


def capture_library_versions() -> dict[str, str]:
    """The interpreter/package versions this run used — a ledger field, not a comment."""
    return {
        "python": platform.python_version(),
        "modal": modal.__version__,
        "genai_corpus": __version__,
    }


@app.function()
def cpu_probe(n: int) -> int:
    """A trivial CPU function this package's one mandated hand-run exercises.

    Not part of the public API (not exported from `__init__.py`): it exists only so
    `scripts/hand_run_spz44.py` has something real to run on Modal, proving the
    harness round-trips through the live service rather than only through mocks.
    """
    return sum(range(n))
