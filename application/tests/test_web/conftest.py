"""Conftest for web tests: ensure the application package is importable."""

import sys
from pathlib import Path

# Insert the application/ directory so `import web.*` and `import dataguard.*`
# resolve regardless of the working directory pytest is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
