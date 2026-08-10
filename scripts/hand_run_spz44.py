"""SPZ-44's one mandated hand-run against live Modal — run manually, never by CI.

Calls `genai_corpus.modal_harness.cpu_probe` once on CPU hardware through
`run_and_measure`, builds a `CostLedger` from the measurement, and writes it to
`fixtures/ledgers/spz-44-hand-run.json` as committed proof the harness round-trips
through the real service, not only through mocks.

Needs `~/.modal.toml` (or `MODAL_TOKEN_ID`/`MODAL_TOKEN_SECRET`) locally. Never wired
into CI or any test — the whole point of `run_and_measure`'s design is that this is
the only place in the repo a Modal call happens, and it happens by hand, once.

Usage: `python scripts/hand_run_spz44.py`
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from genai_corpus.ledger import NOT_APPLICABLE, ledger_to_json, validate_ledger  # noqa: E402
from genai_corpus.modal_harness import (  # noqa: E402
    app,
    capture_library_versions,
    cpu_probe,
    run_and_measure,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "fixtures" / "ledgers" / "spz-44-hand-run.json"
PROBE_N = 1_000_000


def main() -> None:
    with app.run():
        measurement = run_and_measure(lambda: cpu_probe.remote(PROBE_N), hardware="CPU")

    print(f"result: {measurement.result}")
    print(f"cpu_active_seconds: {measurement.cpu_active_seconds}")
    print(f"cost_usd: {measurement.cost_usd}")

    ledger = validate_ledger(
        {
            "unit_id": "SPZ-44-hand-run",
            "schema_version": "1.0",
            "measured_at": datetime.now(UTC).isoformat(),
            "library_versions": capture_library_versions(),
            "hardware": measurement.hardware,
            "model_name": NOT_APPLICABLE,
            "model_precision": NOT_APPLICABLE,
            "input_size_bytes": len(str(PROBE_N).encode()),
            "output_size_bytes": len(str(measurement.result).encode()),
            "assets_processed_count": 1,
            "embedding_or_generation_calls_count": NOT_APPLICABLE,
            "metered_tokens_count": NOT_APPLICABLE,
            "gpu_active_seconds": measurement.gpu_active_seconds,
            "cpu_active_seconds": measurement.cpu_active_seconds,
            # This probe reads and writes nothing outside the RPC call/return itself —
            # no dataset pull, no artifact push — so neither is a measurement, it's a
            # genuine not-applicable, not a zero standing in for "didn't check."
            "storage_bytes": NOT_APPLICABLE,
            "egress_bytes": NOT_APPLICABLE,
            "cache_hit_rate": NOT_APPLICABLE,
            "cost_per_result_usd": measurement.cost_usd,
            "cost_per_1000_results_usd": measurement.cost_usd * 1000,
            "quality_metric_name": NOT_APPLICABLE,
            "quality_metric_value": NOT_APPLICABLE,
            "failure_rate": 0.0,
            "per_unit_metrics": [],
        }
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(ledger_to_json(ledger) + "\n")
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
