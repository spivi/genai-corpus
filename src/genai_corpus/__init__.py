"""genai-corpus — shared corpus loaders for the Generative AI Engineering series.

`SPZ-43` defines this package's shape: a minimal, dependency-free loader over a JSON
manifest, enough to prove the install/import/notebook-smoke-test path against a tiny
fixture corpus. `SPZ-44` adds the standard twelve-line cost-ledger schema on top of
this skeleton; it is deliberately absent here.
"""

from __future__ import annotations

from genai_corpus.corpus import CorpusAsset, load_manifest, verify_checksums

__version__ = "0.1.0"

__all__ = ["CorpusAsset", "__version__", "load_manifest", "verify_checksums"]
