#!/usr/bin/env python3
"""
Transit Intelligence Platform - Scenario-Based Festival Demand Engine

Calculates supplementary fleet surge projections for regional celebrations
under Low, Base, and High scenario assumptions loaded from regional CSV files.

ASSUMPTION NOTICE:
All festival multipliers represent analytical supply-planning assumptions.
They are NOT derived from empirical ridership telemetry (smartcard/ETM)
and serve as baseline scenario inputs for sensitivity and contingency modeling.
"""

import sys
import math
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config

logger = logging.getLogger("ingestion.festivals")


def calculate_extra_buses(current_trips: int, multiplier: float) -> int:
    """Computes extra bus runs required to meet demand multiplier."""
    if current_trips <= 0:
        return 1
    return max(1, math.ceil(current_trips * multiplier) - current_trips)


def determine_priority(multiplier: float, extra_buses: int) -> str:
    """Categorizes dispatch priority based on surge multiplier and volume."""
    if multiplier >= 2.2 or extra_buses >= 15:
        return "CRITICAL (HIGH)"
    if multiplier >= 1.7 or extra_buses >= 8:
        return "MODERATE (MEDIUM)"
    return "STANDARD (LOW)"


def load_festivals_and_recommendations(
    engine: Optional[Engine] = None,
    feed_id: str = "chennai_mtc",
    csv_path: Optional[str] = None
) -> int:
    """
    Loads regional festival calendar CSV and generates fleet surge recommendations
    for the specified feed_id across low, base, and high scenarios.
    """
    if engine is None:
        engine = config.get_db_engine()

    if not csv_path:
        csv_path = str(PROJECT_ROOT / "data" / "festivals" / "tamil_nadu.csv")

    resolved_csv = Path(csv_path)
    if not resolved_csv.is_absolute():
        resolved_csv = PROJECT_ROOT / csv_path

    if not resolved_csv.exists():
        logger.warning("Festival calendar CSV not found at %s. Skipping festival modeling.", resolved_csv)
        return 0

    logger.info("Loading festival calendar from %s for feed '%s'...", resolved_csv, feed_id)
    # Read CSV skipping comments
    df_raw = pd.read_csv(resolved_csv, comment="#").dropna(subset=["festival_name", "date"])

    # Clean existing records for this feed
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM demand_recommendations WHERE feed_id = :feed_id;"),
            {"feed_id": feed_id}
        )
        conn.execute(
            text("DELETE FROM festival_calendar WHERE feed_id = :feed_id;"),
            {"feed_id": feed_id}
        )

    # Prepare festival_calendar records across Low, Base, High scenarios
    scenarios = [
        ("low", "multiplier_low"),
        ("base", "multiplier_base"),
        ("high", "multiplier_high")
    ]

    cal_records = []
    for _, row in df_raw.iterrows():
        f_name = str(row["festival_name"]).strip()
        f_date = datetime.strptime(str(row["date"]).strip(), "%Y-%m-%d").date()
        notes = str(row.get("notes", "")).strip()

        for sc_name, col_mult in scenarios:
            mult_val = float(row.get(col_mult, 1.0))
            cal_records.append({
                "feed_id": feed_id,
                "festival_name": f_name,
                "festival_date": f_date,
                "demand_multiplier": mult_val,
                "scenario": sc_name,
                "notes": f"[{sc_name.upper()} SCENARIO - ASSUMPTION] {notes}"
            })

    if cal_records:
        df_cal = pd.DataFrame(cal_records)
        df_cal.to_sql("festival_calendar", engine, if_exists="append", index=False)
        logger.info("Loaded %d festival calendar rows across 3 scenarios for feed '%s'.", len(df_cal), feed_id)

    # Fetch active routes for this feed
    routes_df = pd.read_sql(
        text("""
            SELECT r.route_id, r.route_short_name, COALESCE(COUNT(t.trip_id), 0) AS current_trip_count
            FROM routes r
            LEFT JOIN trips t ON r.feed_id = t.feed_id AND r.route_id = t.route_id
            WHERE r.feed_id = :feed_id
            GROUP BY r.route_id, r.route_short_name
            ORDER BY r.route_id;
        """),
        engine,
        params={"feed_id": feed_id}
    )

    if routes_df.empty:
        logger.warning("No routes found in database for feed '%s'. Ingest GTFS feed first.", feed_id)
        return 0

    recs = []
    for cal_item in cal_records:
        sc_name = cal_item["scenario"]
        f_name = cal_item["festival_name"]
        f_date = cal_item["festival_date"]
        mult_val = cal_item["demand_multiplier"]

        for _, r in routes_df.iterrows():
            trips = int(r["current_trip_count"])
            extra = calculate_extra_buses(trips, mult_val)
            priority = determine_priority(mult_val, extra)

            recs.append({
                "feed_id": feed_id,
                "scenario": sc_name,
                "route_id": r["route_id"],
                "festival_date": f_date,
                "festival_name": f_name,
                "demand_multiplier": mult_val,
                "current_trip_count": trips,
                "recommended_extra_buses": extra,
                "priority_level": priority,
                "created_at": datetime.now()
            })

    if recs:
        df_recs = pd.DataFrame(recs)
        df_recs.to_sql("demand_recommendations", engine, if_exists="append", index=False, chunksize=1000)
        logger.info("Saved %d scenario recommendations for feed '%s'.", len(df_recs), feed_id)
        return len(df_recs)

    return 0


if __name__ == "__main__":
    config.setup_logging()
    load_festivals_and_recommendations()
