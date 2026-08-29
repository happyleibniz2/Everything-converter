"""Launcher.

Kept as a thin shim so the packaged executable has a stable entry point and so
the project root is importable however the app is started.
"""

import multiprocessing
import os
import sys

# When launched via an absolute path (or a frozen build) the project root is not
# necessarily on sys.path, which would break the top-level package imports.
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app import run

if __name__ == "__main__":
    # Must precede any process spawning in a frozen build, or the executable
    # re-launches itself instead of starting a worker.
    multiprocessing.freeze_support()
    run()
