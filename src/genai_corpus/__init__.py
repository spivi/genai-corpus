"""genai-corpus — shared corpus loaders and cost ledger for the Generative AI
Engineering series.

`SPZ-43` defines the package's shape: a minimal loader over a JSON manifest, enough to
prove the install/import/notebook-smoke-test path against a tiny fixture corpus.
`SPZ-44` adds the standard twelve-line cost-ledger schema, its validator, the article
table serialiser, and the Modal run-and-measure harness on top of that skeleton.
"""

from __future__ import annotations

from genai_corpus._version import __version__
from genai_corpus.corpus import CorpusAsset, load_manifest, verify_checksums
from genai_corpus.ledger import (
    NOT_APPLICABLE,
    CostLedger,
    LedgerValidationError,
    NotApplicable,
    PerUnitMetric,
    ledger_from_json,
    ledger_to_dict,
    ledger_to_json,
    validate_ledger,
)
from genai_corpus.ledger_table import parse_ledger_markdown_table, render_ledger_markdown_table
from genai_corpus.modal_harness import (
    HARDWARE_RATE_USD_PER_SECOND,
    WEIGHTS_VOLUME_MOUNT_PATH,
    WEIGHTS_VOLUME_NAME,
    RunMeasurement,
    capture_library_versions,
    run_and_measure,
    weights_volume,
)

__all__ = [
    "HARDWARE_RATE_USD_PER_SECOND",
    "NOT_APPLICABLE",
    "WEIGHTS_VOLUME_MOUNT_PATH",
    "WEIGHTS_VOLUME_NAME",
    "CorpusAsset",
    "CostLedger",
    "LedgerValidationError",
    "NotApplicable",
    "PerUnitMetric",
    "RunMeasurement",
    "__version__",
    "capture_library_versions",
    "ledger_from_json",
    "ledger_to_dict",
    "ledger_to_json",
    "load_manifest",
    "parse_ledger_markdown_table",
    "render_ledger_markdown_table",
    "run_and_measure",
    "validate_ledger",
    "verify_checksums",
    "weights_volume",
]
