"""Make the repository root importable regardless of how pytest is invoked.

This mirrors ``pytest.ini``'s ``pythonpath = .`` but is robust across pytest
versions and when running a single test file directly.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
