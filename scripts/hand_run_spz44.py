"""SPZ-44's one mandated hand-run against live Modal — run manually, never by CI.

Calls `genai_corpus.modal_harness.cpu_probe` once on CPU hardware through
`run_and_measure`, hands the measurement to `ledger_from_measurement`, and writes the
resulting ledger to `fixtures/ledgers/spz-44-hand-run.json` as committed proof the
harness round-trips through the real service, not only through mocks.

Note what this script does *not* do: hand-copy measured numbers into a ledger literal.
Every measured field arrives through the seam, and the only values written here are
the ones a human genuinely knows and the harness cannot — how many bytes went in, what
came back, and that the single observed call did not fail.

Needs `~/.modal.toml` (or `MODAL_TOKEN_ID`/`MODAL_TOKEN_SECRET`) locally. Never wired
into CI or any test — the whole point of `run_and_measure`'s design is that this is
the only place in the repo a Modal call happens, and it happens by hand, once.

Usage: `python scripts/hand_run_spz44.py`
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from genai_corpus.ledger import ledger_to_json  # noqa: E402
from genai_corpus.modal_harness import (  # noqa: E402
    app,
    cpu_probe,
    hardware_from_function,
    ledger_from_measurement,
    run_and_measure,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "fixtures" / "ledgers" / "spz-44-hand-run.json"
PROBE_N = 1_000_000


def main() -> None:
    hardware = hardware_from_function(cpu_probe)
    with app.run():
        measurement = run_and_measure(
            lambda: cpu_probe.remote(PROBE_N), hardware=hardware, function=cpu_probe
        )

    print(f"result: {measurement.result}")
    print(f"billed_container_seconds: {measurement.billed_container_seconds}")
    print(f"cost_usd: {measurement.cost_usd}")

    ledger = ledger_from_measurement(
        measurement,
        unit_id="SPZ-44-hand-run",
        input_size_bytes=len(str(PROBE_N).encode()),
        output_size_bytes=len(str(measurement.result).encode()),
        assets_processed_count=1,
        # One observed call, zero failures. A rate over a sample of one, stated as
        # such rather than dressed up: it is the only failure evidence this run has.
        failure_rate=0.0,
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(ledger_to_json(ledger) + "\n")
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
