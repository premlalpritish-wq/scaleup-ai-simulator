"""Entry point so the catalogue can be run as ``python -m composition.evidence``.

Keeping the entry point separate avoids the ``RuntimeWarning`` that ``python -m``
emits when the target module is already imported by its package ``__init__``.
"""

from __future__ import annotations

from .catalogue import main

if __name__ == "__main__":
    raise SystemExit(main())