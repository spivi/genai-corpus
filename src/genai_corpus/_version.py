"""Single source for this package's version string.

Lives outside `__init__.py` so `ledger.py` and `modal_harness.py` can import it — for
the ledger's `library_versions` field — without an import cycle back through the
package's own `__init__`.
"""

from __future__ import annotations

__version__ = "0.1.0"
