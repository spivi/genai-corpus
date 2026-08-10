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
    LINE_ITEM_FIELDS,
    NOT_APPLICABLE,
    RESERVED_ROW_LABELS,
    ROW_ORDER,
    SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
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
    CPU_HARDWARE,
    DEFAULT_CPU_REQUEST_CORES,
    DEFAULT_MEMORY_REQUEST_MIB,
    HARDWARE_RATE_USD_PER_SECOND,
    MEMORY_RATE_USD_PER_GIB_SECOND,
    RATE_TABLE_MAX_AGE_DAYS,
    RATE_TABLE_VERIFIED_ON,
    WEIGHTS_VOLUME_MOUNT_PATH,
    WEIGHTS_VOLUME_NAME,
    HardwareMismatchError,
    RunMeasurement,
    capture_library_versions,
    container_request,
    container_request_metrics,
    hardware_from_function,
    ledger_from_measurement,
    rate_table_age_days,
    resolve_hardware_rate,
    run_and_measure,
    weights_volume,
)

__all__ = [
    "CPU_HARDWARE",
    "DEFAULT_CPU_REQUEST_CORES",
    "DEFAULT_MEMORY_REQUEST_MIB",
    "HARDWARE_RATE_USD_PER_SECOND",
    "LINE_ITEM_FIELDS",
    "MEMORY_RATE_USD_PER_GIB_SECOND",
    "NOT_APPLICABLE",
    "RATE_TABLE_MAX_AGE_DAYS",
    "RATE_TABLE_VERIFIED_ON",
    "RESERVED_ROW_LABELS",
    "ROW_ORDER",
    "SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "WEIGHTS_VOLUME_MOUNT_PATH",
    "WEIGHTS_VOLUME_NAME",
    "CorpusAsset",
    "CostLedger",
    "HardwareMismatchError",
    "LedgerValidationError",
    "NotApplicable",
    "PerUnitMetric",
    "RunMeasurement",
    "__version__",
    "capture_library_versions",
    "container_request",
    "container_request_metrics",
    "hardware_from_function",
    "ledger_from_json",
    "ledger_from_measurement",
    "ledger_to_dict",
    "ledger_to_json",
    "load_manifest",
    "parse_ledger_markdown_table",
    "rate_table_age_days",
    "render_ledger_markdown_table",
    "resolve_hardware_rate",
    "run_and_measure",
    "validate_ledger",
    "verify_checksums",
    "weights_volume",
]
