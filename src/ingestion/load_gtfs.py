#!/usr/bin/env python3
"""
Transit Intelligence Platform - GTFS Ingestion Compatibility Wrapper
Delegates to the generic multi-feed pipeline src.ingest with feed_id='chennai_mtc'.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingest import ingest_feed

if __name__ == "__main__":
    ingest_feed("chennai_mtc")
