"""Entry point for ``python -m kinecapture``."""

from __future__ import annotations

import sys

from kinecapture.app import main

if __name__ == "__main__":
    sys.exit(main())
