"""
Data quality checks for GTFS transit feeds.
Runs sanity checks for null identifiers, duplicate keys, orphaned foreign keys,
unserved stops, negative dwell times, and coordinate bounding boxes.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config

logger = logging.getLogger("data.quality")


def run_data_quality_checks(
    engine: Engine,
    feed_id: str = "chennai_mtc",
    feed_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Executes a comprehensive suite of data quality validations against transit_db
    specifically for the given feed_id.
    """
    results: List[Dict[str, Any]] = []

    # Bounding box bounds from config
    bbox = (feed_config or {}).get("bounding_box", {
        "lat_min": 12.80, "lat_max": 13.30,
        "lon_min": 80.00, "lon_max": 80.40
    })
    lat_min = float(bbox.get("lat_min", 10.0))
    lat_max = float(bbox.get("lat_max", 30.0))
    lon_min = float(bbox.get("lon_min", 60.0))
    lon_max = float(bbox.get("lon_max", 95.0))

    with engine.connect() as conn:
        # Check 1: Null values in critical identifiers
        null_counts = conn.execute(text("""
            SELECT 
                (SELECT COUNT(*) FROM routes WHERE feed_id = :fid AND (route_id IS NULL OR route_short_name IS NULL)) AS null_routes,
                (SELECT COUNT(*) FROM stops WHERE feed_id = :fid AND (stop_id IS NULL OR stop_name IS NULL OR stop_lat IS NULL OR stop_lon IS NULL)) AS null_stops,
                (SELECT COUNT(*) FROM trips WHERE feed_id = :fid AND (trip_id IS NULL OR route_id IS NULL OR service_id IS NULL)) AS null_trips,
                (SELECT COUNT(*) FROM stop_times WHERE feed_id = :fid AND (trip_id IS NULL OR stop_id IS NULL OR departure_time IS NULL)) AS null_stop_times;
        """), {"fid": feed_id}).mappings().one()
        
        total_nulls = sum(null_counts.values())
        results.append({
            "check_name": "Null Critical Fields",
            "category": "Completeness",
            "status": "PASS" if total_nulls == 0 else "FAIL",
            "issue_count": total_nulls,
            "details": f"Missing values: routes={null_counts['null_routes']}, stops={null_counts['null_stops']}, trips={null_counts['null_trips']}, stop_times={null_counts['null_stop_times']}"
        })

        # Check 2: Duplicate Primary Keys
        dup_trips = conn.execute(text("""
            SELECT COUNT(*) - COUNT(DISTINCT trip_id) AS dup_trips FROM trips WHERE feed_id = :fid;
        """), {"fid": feed_id}).scalar() or 0

        dup_stop_times = conn.execute(text("""
            SELECT COUNT(*) - COUNT(DISTINCT (trip_id || '-' || stop_sequence::text)) AS dup_st 
            FROM stop_times WHERE feed_id = :fid;
        """), {"fid": feed_id}).scalar() or 0

        total_dups = dup_trips + dup_stop_times
        results.append({
            "check_name": "Duplicate Primary Keys",
            "category": "Uniqueness",
            "status": "PASS" if total_dups == 0 else "FAIL",
            "issue_count": total_dups,
            "details": f"Duplicate trip_ids={dup_trips}, duplicate (trip_id, stop_seq)={dup_stop_times}"
        })

        # Check 3: Orphan Foreign Keys
        orphan_trips = conn.execute(text("""
            SELECT COUNT(*) FROM trips t 
            LEFT JOIN routes r ON t.feed_id = r.feed_id AND t.route_id = r.route_id 
            WHERE t.feed_id = :fid AND r.route_id IS NULL;
        """), {"fid": feed_id}).scalar() or 0

        orphan_stop_times_trips = conn.execute(text("""
            SELECT COUNT(*) FROM stop_times st 
            LEFT JOIN trips t ON st.feed_id = t.feed_id AND st.trip_id = t.trip_id 
            WHERE st.feed_id = :fid AND t.trip_id IS NULL;
        """), {"fid": feed_id}).scalar() or 0

        orphan_stop_times_stops = conn.execute(text("""
            SELECT COUNT(*) FROM stop_times st 
            LEFT JOIN stops s ON st.feed_id = s.feed_id AND st.stop_id = s.stop_id 
            WHERE st.feed_id = :fid AND s.stop_id IS NULL;
        """), {"fid": feed_id}).scalar() or 0

        total_orphans = orphan_trips + orphan_stop_times_trips + orphan_stop_times_stops
        results.append({
            "check_name": "Referential Integrity",
            "category": "Consistency",
            "status": "PASS" if total_orphans == 0 else "FAIL",
            "issue_count": total_orphans,
            "details": f"Orphaned trips={orphan_trips}, orphaned stop_times->trips={orphan_stop_times_trips}, orphaned stop_times->stops={orphan_stop_times_stops}"
        })

        # Check 4: Geospatial Coordinate Bounds
        out_of_bounds_stops = conn.execute(text("""
            SELECT COUNT(*) FROM stops 
            WHERE feed_id = :fid 
              AND (stop_lat NOT BETWEEN :lat_min AND :lat_max 
               OR stop_lon NOT BETWEEN :lon_min AND :lon_max);
        """), {"fid": feed_id, "lat_min": lat_min, "lat_max": lat_max, "lon_min": lon_min, "lon_max": lon_max}).scalar() or 0

        results.append({
            "check_name": "Geospatial Bounding Box",
            "category": "Validity",
            "status": "PASS" if out_of_bounds_stops == 0 else "WARNING",
            "issue_count": out_of_bounds_stops,
            "details": f"Stops outside expected coordinates ({lat_min:.2f}-{lat_max:.2f}N, {lon_min:.2f}-{lon_max:.2f}E): {out_of_bounds_stops}"
        })

        # Check 5: GTFS Overnight Timestamps (Hour >= 24)
        overnight_times = conn.execute(text("""
            SELECT COUNT(*) FROM stop_times 
            WHERE feed_id = :fid 
              AND CAST(SPLIT_PART(departure_time, ':', 1) AS INTEGER) >= 24;
        """), {"fid": feed_id}).scalar() or 0

        results.append({
            "check_name": "GTFS Overnight Timestamps (>=24h)",
            "category": "Validity (GTFS Standard)",
            "status": "INFO",
            "issue_count": overnight_times,
            "details": f"Times past midnight represented as >=24:00:00 (standard GTFS spec): {overnight_times} records"
        })

        # Check 6: Dwell Time Logic (arrival_time > departure_time)
        negative_dwell = conn.execute(text("""
            SELECT COUNT(*) FROM stop_times 
            WHERE feed_id = :fid 
              AND arrival_time > departure_time;
        """), {"fid": feed_id}).scalar() or 0

        results.append({
            "check_name": "Dwell Time Logic",
            "category": "Temporal Consistency",
            "status": "PASS" if negative_dwell == 0 else "FAIL",
            "issue_count": negative_dwell,
            "details": f"Stop times where arrival_time exceeds departure_time: {negative_dwell}"
        })

        # Check 7: Unserved Transit Assets
        unserved_stops = conn.execute(text("""
            SELECT COUNT(*) FROM stops s 
            LEFT JOIN stop_times st ON s.feed_id = st.feed_id AND s.stop_id = st.stop_id 
            WHERE s.feed_id = :fid AND st.stop_id IS NULL;
        """), {"fid": feed_id}).scalar() or 0

        unserved_routes = conn.execute(text("""
            SELECT COUNT(*) FROM routes r 
            LEFT JOIN trips t ON r.feed_id = t.feed_id AND r.route_id = t.route_id 
            WHERE r.feed_id = :fid AND t.route_id IS NULL;
        """), {"fid": feed_id}).scalar() or 0

        total_unserved = unserved_stops + unserved_routes
        results.append({
            "check_name": "Unserved Network Assets",
            "category": "Coverage",
            "status": "INFO" if total_unserved > 0 else "PASS",
            "issue_count": total_unserved,
            "details": f"Unserved stops={unserved_stops}, unserved routes={unserved_routes}"
        })

        # Check 8: Calendar Coverage Gaps
        orphan_calendar_trips = conn.execute(text("""
            SELECT COUNT(*) FROM trips t
            LEFT JOIN calendar c ON t.feed_id = c.feed_id AND t.service_id = c.service_id
            WHERE t.feed_id = :fid AND c.service_id IS NULL;
        """), {"fid": feed_id}).scalar() or 0

        results.append({
            "check_name": "Calendar Service Linkage",
            "category": "Temporal Coverage",
            "status": "PASS" if orphan_calendar_trips == 0 else "FAIL",
            "issue_count": orphan_calendar_trips,
            "details": f"Trips lacking matching calendar service definitions: {orphan_calendar_trips}"
        })

    # Persist findings to PostgreSQL table data_quality_report
    logger.info("Persisting data quality audit results for feed '%s' to database...", feed_id)
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM data_quality_report WHERE feed_id = :fid;"),
            {"fid": feed_id}
        )
        for r in results:
            conn.execute(text("""
                INSERT INTO data_quality_report (feed_id, check_name, category, status, issue_count, details, audited_at)
                VALUES (:feed_id, :check_name, :category, :status, :issue_count, :details, NOW());
            """), {
                "feed_id": feed_id,
                "check_name": r["check_name"],
                "category": r["category"],
                "status": r["status"],
                "issue_count": r["issue_count"],
                "details": r["details"]
            })

    total_failures = sum(1 for r in results if r["status"] == "FAIL")
    total_warnings = sum(1 for r in results if r["status"] == "WARNING")

    summary = {
        "feed_id": feed_id,
        "checks_run": len(results),
        "failures": total_failures,
        "warnings": total_warnings,
        "overall_status": "FAIL" if total_failures > 0 else ("WARNING" if total_warnings > 0 else "PASS"),
        "results": results
    }

    print(f"\n=======================================================")
    print(f" DATA QUALITY AUDIT REPORT - FEED: {feed_id.upper()}")
    print(f"=======================================================")
    for r in results:
        status_flag = f"[{r['status']}]"
        print(f" {status_flag:<10} {r['check_name']:<30} | Issues: {r['issue_count']:<4} | {r['details']}")
    print(f"-------------------------------------------------------")
    print(f" OVERALL AUDIT STATUS: {summary['overall_status']} (Failures: {total_failures}, Warnings: {total_warnings})")
    print(f"=======================================================\n")

    return summary


if __name__ == "__main__":
    config.setup_logging()
    engine = config.get_db_engine()
    run_data_quality_checks(engine, "chennai_mtc")
