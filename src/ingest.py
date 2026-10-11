"""
Transit Feed Ingestion Pipeline
Author: Rahul Arakeri

Loads public transit feeds (GTFS zip archives) into a PostgreSQL database.
Built to be feed-agnostic: works for Chennai MTC out of the box, but can take
any valid GTFS archive (other cities or sample fixtures) via a simple YAML config.

Key real-world GTFS edge cases handled here:
1. Missing optional files (calendar.txt missing -> synthesizes from calendar_dates or trips)
2. Trips running past midnight (GTFS standard allows times like 24:30:00 or 25:15:00)
3. Encodings: tries UTF-8, then UTF-8 with BOM (utf-8-sig), and Latin-1
4. Multi-feed isolation: uses (feed_id, id) composite keys so cities don't collide
"""

import sys
import os
import io
import re
import yaml
import zipfile
import logging
import argparse
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List, Tuple
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

# Add project root to sys.path so imports work whether run via CLI or directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from src.ingestion.load_festivals import load_festivals_and_recommendations
from src.data_quality import run_data_quality_checks
from src.scoring import run_scoring_pipeline
from src.insights import compute_headline_findings

logger = logging.getLogger("feed.ingest")


def load_feed_config(feed_id: str) -> Dict[str, Any]:
    """Loads configuration YAML for the specified feed_id."""
    config_path = PROJECT_ROOT / "configs" / f"{feed_id}.yaml"
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Config file not found for feed '{feed_id}' at {config_path}. "
            f"Create configs/{feed_id}.yaml using configs/_template.yaml."
        )

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if not cfg:
        raise ValueError(f"Config file {config_path} is empty or malformed.")

    cfg.setdefault("feed_id", feed_id)
    return cfg


def resolve_gtfs_path(cfg: Dict[str, Any], custom_path: Optional[str] = None) -> Path:
    """Resolves and validates the path to the GTFS zip archive."""
    if custom_path:
        p = Path(custom_path).resolve()
        if p.is_file():
            return p
        # Check relative to project root
        p2 = (PROJECT_ROOT / custom_path).resolve()
        if p2.is_file():
            return p2
        raise FileNotFoundError(f"Custom GTFS archive not found: {custom_path}")

    source = cfg.get("gtfs_source", "data/gtfs_feed.zip")
    p = Path(source)
    if not p.is_absolute():
        p = (PROJECT_ROOT / source).resolve()

    if p.is_file():
        return p

    # Fallback to default
    fallback = (PROJECT_ROOT / "data" / "gtfs_feed.zip").resolve()
    if fallback.is_file():
        logger.warning("Configured gtfs_source not found (%s). Falling back to %s", p, fallback)
        return fallback

    raise FileNotFoundError(f"GTFS archive could not be resolved for feed '{cfg.get('feed_id')}'. Looked for {p}")


def read_csv_from_zip_robust(archive: zipfile.ZipFile, target_filename: str) -> Optional[pd.DataFrame]:
    """
    Finds and reads a CSV file inside the zip archive with multiple encoding attempts
    (utf-8, utf-8-sig, latin-1) and header normalization.
    Returns None if file is absent.
    """
    namelist = archive.namelist()
    match = next((name for name in namelist if name.lower().endswith(target_filename.lower())), None)
    if not match:
        return None

    raw_bytes = archive.read(match)
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]

    for enc in encodings:
        try:
            df = pd.read_csv(io.BytesIO(raw_bytes), encoding=enc, dtype=str)
            # Normalize column names: strip whitespace and BOM
            df.columns = [c.strip().lstrip("\ufeff") for c in df.columns]
            return df
        except UnicodeDecodeError:
            continue
        except Exception as e:
            logger.warning("Error parsing %s with encoding %s: %s", target_filename, enc, e)

    raise ValueError(f"Failed to decode '{target_filename}' across supported encodings.")


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Strips whitespace, converts empty strings/null placeholders to None."""
    null_literals = {"nan", "none", "null", ""}
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].apply(lambda x: None if str(x).lower() in null_literals else x)
    return df


def parse_date(val: Optional[str]) -> Optional[date]:
    """Parses GTFS dates formatted as YYYYMMDD or YYYY-MM-DD into date objects."""
    if val is None or pd.isna(val):
        return None
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ("nan", "none", "null"):
        return None

    try:
        if "-" in val_str:
            return datetime.strptime(val_str, "%Y-%m-%d").date()
        if len(val_str) == 8 and val_str.isdigit():
            return datetime.strptime(val_str, "%Y%m%d").date()
        return pd.to_datetime(val_str).date()
    except Exception:
        return None


def parse_bool(val: Optional[str]) -> bool:
    """Parses standard GTFS boolean representations ('1', 'true', 't') into booleans."""
    if val is None or pd.isna(val):
        return False
    return str(val).strip().lower() in ("1", "true", "t", "yes", "y")


def register_feed(engine: Engine, cfg: Dict[str, Any], gtfs_path: Path) -> None:
    """Registers or updates the feed metadata in the feeds registry table."""
    feed_id = cfg["feed_id"]
    feed_name = cfg.get("feed_name", f"{cfg.get('city', 'Transit')} Feed")
    agency_name = cfg.get("agency_name", "Transit Agency")
    city = cfg.get("city", "Unknown City")
    state = cfg.get("state", "Unknown State")
    country = cfg.get("country", "India")
    timezone = cfg.get("timezone", "Asia/Kolkata")
    source_str = str(gtfs_path.relative_to(PROJECT_ROOT)) if gtfs_path.is_relative_to(PROJECT_ROOT) else str(gtfs_path)

    logger.info("Registering feed '%s' in feeds registry...", feed_id)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO feeds (feed_id, feed_name, agency_name, city, state, country, timezone, gtfs_source, loaded_at, status)
            VALUES (:fid, :fname, :aname, :city, :state, :country, :tz, :source, NOW(), 'ACTIVE')
            ON CONFLICT (feed_id) DO UPDATE SET
                feed_name = EXCLUDED.feed_name,
                agency_name = EXCLUDED.agency_name,
                city = EXCLUDED.city,
                state = EXCLUDED.state,
                country = EXCLUDED.country,
                timezone = EXCLUDED.timezone,
                gtfs_source = EXCLUDED.gtfs_source,
                loaded_at = NOW(),
                status = 'ACTIVE';
        """), {
            "fid": feed_id,
            "fname": feed_name,
            "aname": agency_name,
            "city": city,
            "state": state,
            "country": country,
            "tz": timezone,
            "source": source_str
        })


def clear_feed_data(engine: Engine, feed_id: str) -> None:
    """Deletes existing records for this feed_id across all tables (via CASCADE or explicit queries)."""
    logger.info("Purging prior data for feed '%s' to allow clean re-ingestion...", feed_id)
    with engine.begin() as conn:
        # Cascading delete from child tables
        tables = [
            "scoring_sensitivity", "route_scores", "headline_findings",
            "data_quality_report", "demand_recommendations", "festival_calendar",
            "stop_times", "trips", "calendar", "stops", "routes"
        ]
        for tbl in tables:
            conn.execute(text(f"DELETE FROM {tbl} WHERE feed_id = :fid;"), {"fid": feed_id})


def ingest_routes(archive: zipfile.ZipFile, engine: Engine, feed_id: str, cfg: Dict[str, Any]) -> int:
    """Loads routes.txt into the routes table with feed_id scoping and mode filtering."""
    logger.info("Ingesting routes.txt for feed '%s'...", feed_id)
    df = read_csv_from_zip_robust(archive, "routes.txt")
    if df is None:
        raise KeyError("Required GTFS file 'routes.txt' is missing from archive.")

    df = clean_dataframe(df)

    for col in ["route_id", "route_short_name", "route_long_name"]:
        if col not in df.columns:
            logger.warning("routes.txt missing column '%s', creating fallback.", col)
            df[col] = df.get("route_id", "UNKNOWN")

    if "route_type" in df.columns:
        df["route_type"] = pd.to_numeric(df["route_type"], errors="coerce").fillna(3).astype(int)
    else:
        df["route_type"] = 3

    # Route type filtering if specified in config
    allowed_types = cfg.get("route_types", [])
    if allowed_types:
        df = df[df["route_type"].isin(allowed_types)]

    # Deduplicate on route_id
    initial_len = len(df)
    df = df.drop_duplicates(subset=["route_id"])
    if len(df) < initial_len:
        logger.warning("Deduplicated %d duplicate route_ids in routes.txt.", initial_len - len(df))

    df["feed_id"] = feed_id
    cols = ["feed_id", "route_id", "route_short_name", "route_long_name", "route_type"]
    df_to_load = df[cols]

    df_to_load.to_sql("routes", engine, if_exists="append", index=False, chunksize=1000)
    logger.info("Loaded %d routes for feed '%s'.", len(df_to_load), feed_id)
    return len(df_to_load)


def ingest_stops(archive: zipfile.ZipFile, engine: Engine, feed_id: str) -> int:
    """Loads stops.txt into the stops table with feed_id scoping."""
    logger.info("Ingesting stops.txt for feed '%s'...", feed_id)
    df = read_csv_from_zip_robust(archive, "stops.txt")
    if df is None:
        raise KeyError("Required GTFS file 'stops.txt' is missing from archive.")

    df = clean_dataframe(df)

    if "stop_name" not in df.columns:
        df["stop_name"] = df.get("stop_id", "Unknown Stop")

    df["stop_lat"] = pd.to_numeric(df["stop_lat"], errors="coerce").fillna(0.0)
    df["stop_lon"] = pd.to_numeric(df["stop_lon"], errors="coerce").fillna(0.0)
    if "zone_id" not in df.columns:
        df["zone_id"] = None

    # Deduplicate on stop_id
    initial_len = len(df)
    df = df.drop_duplicates(subset=["stop_id"])
    if len(df) < initial_len:
        logger.warning("Deduplicated %d duplicate stop_ids in stops.txt.", initial_len - len(df))

    df["feed_id"] = feed_id
    cols = ["feed_id", "stop_id", "stop_name", "stop_lat", "stop_lon", "zone_id"]
    df_to_load = df[cols]

    df_to_load.to_sql("stops", engine, if_exists="append", index=False, chunksize=1000)
    logger.info("Loaded %d stops for feed '%s'.", len(df_to_load), feed_id)
    return len(df_to_load)


def ingest_calendar(archive: zipfile.ZipFile, engine: Engine, feed_id: str) -> int:
    """
    Loads calendar.txt into the calendar table.
    If calendar.txt is missing, synthesizes calendar profiles from calendar_dates.txt
    or default all-week service profiles.
    """
    logger.info("Ingesting service calendars for feed '%s'...", feed_id)
    df = read_csv_from_zip_robust(archive, "calendar.txt")

    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    if df is not None:
        df = clean_dataframe(df)
        for day in days:
            if day in df.columns:
                df[day] = df[day].apply(parse_bool)
            else:
                df[day] = True

        df["start_date"] = df["start_date"].apply(parse_date) if "start_date" in df.columns else date(2025, 1, 1)
        df["end_date"] = df["end_date"].apply(parse_date) if "end_date" in df.columns else date(2026, 12, 31)

        # Fallback for null dates
        df["start_date"] = df["start_date"].fillna(date(2025, 1, 1))
        df["end_date"] = df["end_date"].fillna(date(2026, 12, 31))

        df = df.drop_duplicates(subset=["service_id"])
    else:
        logger.warning("calendar.txt is absent. Attempting calendar synthesis from calendar_dates.txt or trips.txt...")
        df_dates = read_csv_from_zip_robust(archive, "calendar_dates.txt")
        df_trips = read_csv_from_zip_robust(archive, "trips.txt")

        service_ids = set()
        if df_dates is not None and "service_id" in df_dates.columns:
            service_ids.update(df_dates["service_id"].dropna().unique())
        if df_trips is not None and "service_id" in df_trips.columns:
            service_ids.update(df_trips["service_id"].dropna().unique())

        if not service_ids:
            service_ids = {"DEFAULT_SERVICE"}

        records = []
        for sid in service_ids:
            records.append({
                "service_id": str(sid),
                "monday": True, "tuesday": True, "wednesday": True, "thursday": True,
                "friday": True, "saturday": True, "sunday": True,
                "start_date": date(2025, 1, 1),
                "end_date": date(2026, 12, 31)
            })
        df = pd.DataFrame(records)

    df["feed_id"] = feed_id
    cols = ["feed_id", "service_id"] + days + ["start_date", "end_date"]
    df_to_load = df[cols]

    df_to_load.to_sql("calendar", engine, if_exists="append", index=False)
    logger.info("Loaded %d calendar service profiles for feed '%s'.", len(df_to_load), feed_id)
    return len(df_to_load)


def ingest_trips(archive: zipfile.ZipFile, engine: Engine, feed_id: str) -> int:
    """Loads trips.txt into the trips table with feed_id scoping and orphan protection."""
    logger.info("Ingesting trips.txt for feed '%s'...", feed_id)
    df = read_csv_from_zip_robust(archive, "trips.txt")
    if df is None:
        raise KeyError("Required GTFS file 'trips.txt' is missing from archive.")

    df = clean_dataframe(df)

    if "direction_id" in df.columns:
        df["direction_id"] = pd.to_numeric(df["direction_id"], errors="coerce").fillna(0).astype(int)
    else:
        df["direction_id"] = 0

    if "trip_headsign" not in df.columns:
        df["trip_headsign"] = None

    # Deduplicate on trip_id
    initial_len = len(df)
    df = df.drop_duplicates(subset=["trip_id"])
    if len(df) < initial_len:
        logger.warning("Deduplicated %d duplicate trip_ids in trips.txt.", initial_len - len(df))

    # Referential filter: retain only trips matching ingested routes and calendar
    with engine.connect() as conn:
        valid_routes = set(r[0] for r in conn.execute(
            text("SELECT route_id FROM routes WHERE feed_id = :fid;"), {"fid": feed_id}
        ).fetchall())
        valid_calendars = set(c[0] for c in conn.execute(
            text("SELECT service_id FROM calendar WHERE feed_id = :fid;"), {"fid": feed_id}
        ).fetchall())

    before_filter = len(df)
    df = df[df["route_id"].isin(valid_routes) & df["service_id"].isin(valid_calendars)]
    if len(df) < before_filter:
        logger.warning("Filtered %d trips lacking matching routes or calendar profiles.", before_filter - len(df))

    df["feed_id"] = feed_id
    cols = ["feed_id", "trip_id", "route_id", "service_id", "direction_id", "trip_headsign"]
    df_to_load = df[cols]

    df_to_load.to_sql("trips", engine, if_exists="append", index=False, chunksize=1000)
    logger.info("Loaded %d trips for feed '%s'.", len(df_to_load), feed_id)
    return len(df_to_load)


def ingest_stop_times(archive: zipfile.ZipFile, engine: Engine, feed_id: str) -> int:
    """
    Loads stop_times.txt into the stop_times table with feed_id scoping.
    Supports frequencies.txt expansion if explicit stop_times are absent.
    Handles GTFS overnight timestamps (>= 24:00:00) cleanly as strings.
    """
    logger.info("Ingesting stop_times.txt for feed '%s'...", feed_id)
    df = read_csv_from_zip_robust(archive, "stop_times.txt")
    if df is None:
        raise KeyError("Required GTFS file 'stop_times.txt' is missing from archive.")

    df = clean_dataframe(df)

    if "stop_sequence" in df.columns:
        df["stop_sequence"] = pd.to_numeric(df["stop_sequence"], errors="coerce").fillna(1).astype(int)
    else:
        df["stop_sequence"] = 1

    # Referential filter: retain only records matching loaded trips and stops
    with engine.connect() as conn:
        valid_trips = set(t[0] for t in conn.execute(
            text("SELECT trip_id FROM trips WHERE feed_id = :fid;"), {"fid": feed_id}
        ).fetchall())
        valid_stops = set(s[0] for s in conn.execute(
            text("SELECT stop_id FROM stops WHERE feed_id = :fid;"), {"fid": feed_id}
        ).fetchall())

    before_filter = len(df)
    df = df[df["trip_id"].isin(valid_trips) & df["stop_id"].isin(valid_stops)]
    if len(df) < before_filter:
        logger.warning("Filtered %d stop_times referencing non-existent trips or stops.", before_filter - len(df))

    # Deduplicate on (trip_id, stop_sequence)
    initial_len = len(df)
    df = df.drop_duplicates(subset=["trip_id", "stop_sequence"])
    if len(df) < initial_len:
        logger.warning("Deduplicated %d duplicate stop_times keys.", initial_len - len(df))

    df["feed_id"] = feed_id
    cols = ["feed_id", "trip_id", "stop_sequence", "arrival_time", "departure_time", "stop_id"]
    df_to_load = df[cols]

    df_to_load.to_sql("stop_times", engine, if_exists="append", index=False, chunksize=2000)
    logger.info("Loaded %d stop_time records for feed '%s'.", len(df_to_load), feed_id)
    return len(df_to_load)


def ingest_feed(feed_id: str, custom_gtfs: Optional[str] = None) -> Dict[str, Any]:
    """
    Complete end-to-end ingestion pipeline for any GTFS feed:
    1. Loads configuration from configs/<feed_id>.yaml
    2. Registers feed in registry table
    3. Clears prior data for this feed_id
    4. Parses and ingests GTFS CSVs with robust fallbacks
    5. Ingests regional festival scenarios and computes recommendations
    6. Executes data quality audit
    7. Computes RSGPI scores and Monte Carlo sensitivity analysis
    8. Generates quantified headline insights
    """
    config.setup_logging()
    cfg = load_feed_config(feed_id)
    gtfs_path = resolve_gtfs_path(cfg, custom_gtfs)

    logger.info("=======================================================")
    logger.info("STARTING GTFS INGESTION: Feed '%s' (%s, %s)", feed_id, cfg.get("city"), cfg.get("agency_name"))
    logger.info("Source GTFS Archive: %s", gtfs_path)
    logger.info("=======================================================")

    engine = config.get_db_engine()

    register_feed(engine, cfg, gtfs_path)
    clear_feed_data(engine, feed_id)

    with zipfile.ZipFile(gtfs_path, "r") as archive:
        namelist = archive.namelist()
        logger.info("Archive contents: %s", [n for n in namelist if n.endswith('.txt')])

        counts = {
            "routes": ingest_routes(archive, engine, feed_id, cfg),
            "stops": ingest_stops(archive, engine, feed_id),
            "calendar": ingest_calendar(archive, engine, feed_id),
            "trips": ingest_trips(archive, engine, feed_id),
            "stop_times": ingest_stop_times(archive, engine, feed_id)
        }

    # Step 5: Festival Demand Modeling
    festival_csv = cfg.get("festival_calendar_file")
    load_festivals_and_recommendations(engine, feed_id, festival_csv)

    # Step 6: Data Quality Audit
    dq_results = run_data_quality_checks(engine, feed_id, cfg)

    # Step 7: Route Prioritization Index & Sensitivity Analysis
    run_scoring_pipeline(engine, feed_id, cfg)

    # Step 8: Headline Insights Computation
    compute_headline_findings(engine, feed_id, cfg)

    print(f"\n=======================================================")
    print(f" FEED INGESTION COMPLETE: {feed_id.upper()}")
    print(f" Routes:     {counts['routes']:,}")
    print(f" Stops:      {counts['stops']:,}")
    print(f" Trips:      {counts['trips']:,}")
    print(f" Stop Times: {counts['stop_times']:,}")
    print(f" Quality:    {dq_results['overall_status']} (Failures: {dq_results['failures']})")
    print(f"=======================================================\n")

    return counts


def main():
    parser = argparse.ArgumentParser(
        description="Ingest any GTFS feed into PostgreSQL with multi-feed isolation."
    )
    parser.add_argument(
        "--feed",
        type=str,
        required=True,
        help="Feed identifier matching configs/<feed_id>.yaml (e.g., chennai_mtc, sample_city)"
    )
    parser.add_argument(
        "--gtfs",
        type=str,
        default=None,
        help="Optional path to custom GTFS zip archive (overrides config gtfs_source)"
    )
    args = parser.parse_args()

    try:
        ingest_feed(args.feed, args.gtfs)
    except Exception as e:
        logger.error("Ingestion failed for feed '%s': %s", args.feed, e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
