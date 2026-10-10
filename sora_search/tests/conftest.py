# -*- coding: utf-8 -*-
"""Make the project root importable so tests can `import sora_search`."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # SoraSearch-mcp/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
