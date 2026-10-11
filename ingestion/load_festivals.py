#!/usr/bin/env python3
"""
Wrapper for Festival Demand Intelligence Pipeline.
Delegates to src/ingestion/load_festivals.py for modular execution.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.load_festivals import load_festivals_and_recommendations

if __name__ == "__main__":
    load_festivals_and_recommendations()
