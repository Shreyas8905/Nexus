import os
import sys
from pathlib import Path

# Make `app` importable when running `pytest` from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Tests always run against development defaults (no real secrets needed).
os.environ.setdefault("ENV", "development")
