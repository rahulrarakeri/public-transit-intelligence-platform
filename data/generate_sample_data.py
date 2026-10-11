#!/usr/bin/env python3
"""
Transit Intelligence Platform - Mock Data Generator

Utility script for generating synthetic GTFS datasets for offline development,
testing, and benchmarking.
"""

import sys
import argparse
import logging
import math
import random
import zipfile
import io
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Tuple, List, Dict
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config

logger = logging.getLogger("data.generator")

# Representative route identifiers for the metropolitan region
ROUTE_NUMBERS = [
    "1", "1A", "1B", "2", "2A", "5", "5C", "9", "11", "12",
    "12A", "15", "15A", "17A", "18", "21", "23", "23C", "25G", "27",
    "29", "32", "33", "37", "41", "47", "47A", "47B", "52", "57",
    "58", "70", "70A", "70V", "79", "87", "88", "100", "109", "119",
    "127", "500", "500A", "M70", "M79", "E1", "E2", "E3", "E4", "E5"
]

# Major stop landmarks across northern, central, and southern corridors
STOP_NAMES = [
    "Koyambedu Bus Terminus", "Tambaram Bus Stand", "Guindy", "T Nagar Bus Stand", "Adyar",
    "Anna Nagar Tower", "Perambur", "Chromepet", "Velachery", "Sholinganallur",
    "Porur", "Ambattur", "Avadi", "Poonamallee", "Mogappair",
    "Madhavaram", "Thiruvottiyur", "Ennore", "Manali", "Royapuram",
    "Central Railway Station", "Egmore", "Broadway", "Mylapore", "Nungambakkam",
    "Chetpet", "Kilpauk", "Villivakkam", "Tondiarpet", "Washermanpet",
    "Saidapet", "Ashok Nagar", "KK Nagar", "Virugambakkam", "Valasaravakkam",
    "Nerkundram", "Padi", "Kolathur", "Villapuram", "Selaiyur",
    "Pallavaram", "Pammal", "Anakaputhur", "Mangadu", "Kundrathur",
    "Gerugambakkam", "Paranur", "Urapakkam", "Guduvanchery", "Vandalur",
    "Perungalathur", "Mudichur", "Thirumudivakkam", "Sembakkam", "Medavakkam",
    "Perumbakkam", "Navalur", "Siruseri", "Kelambakkam", "Thiruporur",
    "Mahabalipuram Road", "Kovalam", "Neelankarai", "Palavakkam", "Injambakkam",
    "Uthandi", "Kanathur", "ECR", "OMR", "IT Corridor",
    "Perungudi", "Taramani", "Thiruvanmiyur", "Besant Nagar", "Elliot Beach",
    "Luz", "Triplicane", "Chepauk", "Ice House", "Foreshore Estate",
    "Marina Beach", "Light House", "Fort St George", "Rajaji Salai", "NSC Bose Road",
    "Mint", "Vepery", "Purasaiwakkam", "Choolai", "Flower Bazaar",
    "Parrys Corner", "High Court", "Parry's", "George Town", "Govindappa Naicken Street",
    "Santhome Cathedral", "Alwarpet", "Mandaveli", "Kotturpuram", "Chamiers Road",
    "R.A. Puram", "Teynampet", "Thousand Lights", "Gopalapuram", "Royapettah",
    "Kodambakkam", "Vadapalani", "Saligramam", "Chinmaya Nagar", "Koyambedu Market",
    "Arumbakkam", "Aminjikarai", "Shenoy Nagar", "Anna Arch", "Thirumangalam",
    "Anna Nagar West", "Mogappair East", "Mogappair West", "Ambattur OT", "Ambattur Estate",
    "Korattur", "Pattaravakkam", "Villivakkam Railway Station", "ICF Colony", "Ayanavaram",
    "Otteri", "Pattalam", "Perambur Barracks", "Jamalia", "Peravallur",
    "Retteri", "Madhavaram Roundabout", "MKB Nagar", "Vyasarpadi", "Basin Bridge",
    "Stanley Hospital", "Royapuram Bridge", "Kasimedu", "Kaladipet", "Tollgate",
    "Theradi", "Ajax", "Wimco Nagar", "Ernavoor", "Manali New Town",
    "Red Hills", "Puzhal", "Surapet", "Vinayagapuram", "Lakshmipuram"
]


def generate_stops(count: int = 150, seed: int = 42) -> pd.DataFrame:
    """Generates synthetic bus stops within geographic bounds [12.90-13.20N, 80.10-80.30E]."""
    random.seed(seed)
    stops = []
    names = STOP_NAMES[:count] if count <= len(STOP_NAMES) else (STOP_NAMES * (count // len(STOP_NAMES) + 1))[:count]

    for idx, name in enumerate(names, start=1):
        lat = round(random.uniform(12.9100, 13.1500), 6)
        lon = round(random.uniform(80.1200, 80.2800), 6)
        stops.append({
            "stop_id": f"STOP_{idx:03d}",
            "stop_name": name,
            "stop_lat": lat,
            "stop_lon": lon,
            "zone_id": f"ZONE_{((idx - 1) % 5) + 1}"
        })

    return pd.DataFrame(stops)


def generate_routes(count: int = 50, seed: int = 101) -> pd.DataFrame:
    """Generates routes with origin-destination corridor descriptions."""
    random.seed(seed)
    hubs = ["Koyambedu", "Tambaram", "Broadway", "Central Station", "T Nagar", "Adyar", "Velachery", "Avadi"]
    vias = ["Guindy", "Ashok Nagar", "Saidapet", "Mylapore", "Anna Nagar", "Porur", "OMR"]

    routes = []
    codes = ROUTE_NUMBERS[:count] if count <= len(ROUTE_NUMBERS) else [f"R{i}" for i in range(1, count + 1)]

    for idx, short_name in enumerate(codes, start=1):
        orig = random.choice(hubs)
        dest = random.choice([h for h in hubs if h != orig])
        via = random.choice(vias)
        routes.append({
            "route_id": f"ROUTE_{idx:02d}",
            "route_short_name": short_name,
            "route_long_name": f"{orig} to {dest} via {via}",
            "route_type": 3
        })

    return pd.DataFrame(routes)


def generate_calendar() -> pd.DataFrame:
    """Generates standard calendar service profiles."""
    start = date(2025, 1, 1)
    end = date(2026, 12, 31)
    return pd.DataFrame([
        {
            "service_id": "c_daily",
            "monday": True, "tuesday": True, "wednesday": True,
            "thursday": True, "friday": True, "saturday": True, "sunday": True,
            "start_date": start, "end_date": end
        },
        {
            "service_id": "c_weekday",
            "monday": True, "tuesday": True, "wednesday": True,
            "thursday": True, "friday": True, "saturday": False, "sunday": False,
            "start_date": start, "end_date": end
        },
        {
            "service_id": "c_weekend",
            "monday": False, "tuesday": False, "wednesday": False,
            "thursday": False, "friday": False, "saturday": True, "sunday": True,
            "start_date": start, "end_date": end
        }
    ])


def generate_trips_and_stops(
    df_routes: pd.DataFrame,
    df_stops: pd.DataFrame,
    total_trips: int = 500,
    stops_per_trip: int = 10,
    seed: int = 2025
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Generates scheduled trips with morning/evening peak distributions and sequential stop times."""
    random.seed(seed)
    route_ids = df_routes["route_id"].tolist()
    all_stops = df_stops["stop_id"].tolist()

    trips = []
    stop_times = []

    for t_idx in range(1, total_trips + 1):
        trip_id = f"TRIP_{t_idx:04d}"
        route_id = route_ids[(t_idx - 1) % len(route_ids)]
        service_id = "c_weekday" if t_idx % 6 == 0 else "c_daily"
        direction_id = random.choice([0, 1])

        trips.append({
            "trip_id": trip_id,
            "route_id": route_id,
            "service_id": service_id,
            "direction_id": direction_id,
            "trip_headsign": "City Terminus"
        })

        # Peak hour distribution: 35% morning (7-9), 35% evening (17-19), 30% off-peak
        rand = random.random()
        if rand < 0.35:
            hour = random.randint(7, 9)
        elif rand < 0.70:
            hour = random.randint(17, 19)
        else:
            hour = random.choice([5, 6, 10, 11, 12, 13, 14, 15, 16, 20, 21])

        curr_time = datetime(2025, 1, 1, hour, random.randint(0, 59), 0)
        start_idx = random.randint(0, max(0, len(all_stops) - stops_per_trip))
        seq_stops = all_stops[start_idx : start_idx + stops_per_trip]

        for seq, s_id in enumerate(seq_stops, start=1):
            arr = curr_time.strftime("%H:%M:%S")
            curr_time += timedelta(seconds=30)
            dep = curr_time.strftime("%H:%M:%S")

            stop_times.append({
                "trip_id": trip_id,
                "stop_sequence": seq,
                "arrival_time": arr,
                "departure_time": dep,
                "stop_id": s_id
            })
            curr_time += timedelta(minutes=random.randint(3, 5))

    return pd.DataFrame(trips), pd.DataFrame(stop_times)


def export_zip(
    output_path: Path,
    df_routes: pd.DataFrame,
    df_stops: pd.DataFrame,
    df_calendar: pd.DataFrame,
    df_trips: pd.DataFrame,
    df_stop_times: pd.DataFrame
) -> None:
    """Writes the generated DataFrames into standard GTFS CSV text files within a zip."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Writing GTFS zip archive to: %s", output_path)

    files = {
        "routes.txt": df_routes,
        "stops.txt": df_stops,
        "calendar.txt": df_calendar,
        "trips.txt": df_trips,
        "stop_times.txt": df_stop_times
    }

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, df in files.items():
            buf = io.StringIO()
            df.to_csv(buf, index=False)
            zf.writestr(fname, buf.getvalue())
            logger.info("Packed %s (%d rows)", fname, len(df))

    logger.info("Successfully exported mock GTFS feed.")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic GTFS test data.")
    parser.add_argument("--routes", type=int, default=50, help="Number of routes to generate")
    parser.add_argument("--stops", type=int, default=150, help="Number of stops to generate")
    parser.add_argument("--trips", type=int, default=500, help="Number of trips to generate")
    parser.add_argument("--output-zip", type=str, default="data/synthetic_sample_feed.zip", help="Output zip file path")
    parser.add_argument("--seed", type=int, default=42, help="Random generator seed")
    args = parser.parse_args()

    config.setup_logging()
    logger.info("Generating synthetic GTFS feed (%d routes, %d stops, %d trips)...", args.routes, args.stops, args.trips)

    df_stops = generate_stops(count=args.stops, seed=args.seed)
    df_routes = generate_routes(count=args.routes, seed=args.seed)
    df_calendar = generate_calendar()
    df_trips, df_stop_times = generate_trips_and_stops(df_routes, df_stops, total_trips=args.trips, seed=args.seed)

    out_path = Path(args.output_zip).resolve()
    export_zip(out_path, df_routes, df_stops, df_calendar, df_trips, df_stop_times)
    logger.info("Done. Output available at %s", out_path)


if __name__ == "__main__":
    main()
