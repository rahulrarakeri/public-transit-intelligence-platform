# Onboarding a New Transit Feed (Zero Code Changes)

The **Public Transit Intelligence Platform** is built on a feed-agnostic, multi-city architecture. Adding a new metropolitan transit agency or city requires **only a configuration file and a GTFS archive**—no code modifications.

---

## 🏗️ Architecture Overview

The platform uses composite database keys `(feed_id, id)` across all PostgreSQL tables. Multiple cities (e.g., Chennai, Bengaluru, Delhi, London, or synthetic test fixtures) can coexist simultaneously in the database without ID collisions.

When you ingest a feed, the platform automatically:
1. Registers the agency in the `feeds` registry table.
2. Robustly parses the GTFS zip (handling optional files, overnight $>24\text{h}$ times, encodings, and deduplication).
3. Evaluates 8 automated data quality checks.
4. Simulates regional holiday surge requirements across Low, Base, and High scenarios.
5. Computes the **Route Supply Gap Priority Index (RSGPI)** with a 500-run Monte Carlo sensitivity audit.
6. Derives empirical headline findings and registers the feed for dashboard benchmarking.

---

## 📋 Step-by-Step Onboarding Guide

### Step 1: Obtain the GTFS Feed Archive
Place your valid GTFS zip archive into the `data/` directory (e.g., `data/bengaluru_bmtc.zip`) or keep it at any accessible local path.

Standard GTFS files handled:
- `routes.txt` (Required)
- `stops.txt` (Required)
- `trips.txt` (Required)
- `stop_times.txt` (Required)
- `calendar.txt` (Optional — if missing, synthesized from `calendar_dates.txt` or default active schedules)
- `agency.txt`, `shapes.txt`, `frequencies.txt` (Optional — parsed gracefully)

---

### Step 2: Define Regional Festival Calendar (Optional / Recommended)
If your region observes distinct festive holidays (e.g., Karnataka Rajyotsava, Durga Puja, Ganesh Utsav), create `data/festivals/<region>.csv` using `data/festivals/_template.csv`:

```csv
festival_name,date,region,multiplier_low,multiplier_base,multiplier_high,notes
State Foundation Day,2025-11-01,Karnataka,1.4,1.8,2.2,Parades gatherings and regional intercity movements
Annual Harvest Gala,2025-01-15,Karnataka,1.5,2.0,2.5,Intercity terminal transit surges
```

> [!NOTE]
> All multipliers represent analytical planning assumptions for scenario stress-testing, not empirical ticketing telemetry.

---

### Step 3: Create Feed Configuration (`configs/<feed_id>.yaml`)
Copy `configs/_template.yaml` to `configs/<your_feed_id>.yaml` (e.g., `configs/bengaluru_bmtc.yaml`):

```yaml
feed_id: "bengaluru_bmtc"
feed_name: "BMTC Bus Network"
agency_name: "Bangalore Metropolitan Transport Corporation"
city: "Bengaluru"
state: "Karnataka"
country: "India"
timezone: "Asia/Kolkata"

gtfs_source: "data/bengaluru_bmtc.zip"

bounding_box:
  lat_min: 12.80
  lat_max: 13.20
  lon_min: 77.40
  lon_max: 77.80

peak_hours:
  morning_peak: [8, 9, 10]      # 08:00 - 11:00
  evening_peak: [17, 18, 19]    # 17:00 - 20:00

thresholds:
  high_headway_minutes: 30.0
  severe_off_peak_headway_minutes: 240.0
  top_hubs_count: 10

route_types: [3]  # 3 = Bus. Leave empty [] for multi-modal networks.

festival_calendar_file: "data/festivals/sample_region.csv"

scoring_weights:
  network_connectivity: 0.35
  off_peak_gap: 0.35
  weekend_deficit: 0.15
  stop_density: 0.15

sensitivity_analysis:
  iterations: 500
  perturbation_range: 0.20
```

---

### Step 4: Run the Ingestion Pipeline
Execute the CLI to ingest the feed into PostgreSQL:

```bash
# Using the path configured in configs/bengaluru_bmtc.yaml:
python -m src.ingest --feed bengaluru_bmtc

# Or explicitly overriding the GTFS archive path:
python -m src.ingest --feed bengaluru_bmtc --gtfs /path/to/custom_feed.zip
```

The pipeline will print:
```text
=======================================================
 DATA QUALITY AUDIT REPORT - FEED: BENGALURU_BMTC
=======================================================
 [PASS]     Null Critical Fields           | Issues: 0
 [PASS]     Duplicate Primary Keys         | Issues: 0
 [PASS]     Referential Integrity          | Issues: 0
 [PASS]     Geospatial Bounding Box        | Issues: 0
-------------------------------------------------------
 OVERALL AUDIT STATUS: PASS (Failures: 0, Warnings: 0)
=======================================================
 FEED INGESTION COMPLETE: BENGALURU_BMTC
 Routes: 120 | Stops: 850 | Trips: 2,400
=======================================================
```

---

### Step 5: Launch the Dashboard & Benchmark
Start the Streamlit application:
```bash
streamlit run app/app.py
```

1. **Sidebar Selector:** Select `Bengaluru (Bangalore Metropolitan Transport Corporation)` from the feed selector to view its independent **Executive Summary**, **Network Topology**, **Corridor Performance**, and **Route Prioritization Scores**.
2. **City Comparison Page:** Navigate to `🏙️ City Comparison` to benchmark Bengaluru against Chennai MTC across normalized supply metrics (trips per corridor, % peak compression, % weekend shutoff, hub concentration).
3. **Feed Registry Page:** Inspect data quality status and row counts in `📋 Feed Registry & Health`.

---

## 🛠️ Handling Real-World Feed Anomalies

| GTFS Variation | How the Platform Handles It |
|---|---|
| **Missing `calendar.txt`** | Automatically detects presence of `calendar_dates.txt` or `trips.txt` and synthesizes weekly service profiles. |
| **Overnight Trips ($\ge 24\text{h}$)** | Timestamps like `24:15:00` are stored as strings and converted gracefully using modulo 24 parsing. |
| **Missing Optional Files** | `shapes.txt`, `frequencies.txt`, and `transfers.txt` are optional. The pipeline logs their absence and continues without crashing. |
| **Non-UTF-8 Encoding** | Ingestion automatically falls back to `utf-8-sig` (BOM removal), `latin-1`, and `cp1252`. |
| **Duplicate IDs** | Automatically cleans and logs duplicate `route_id`, `stop_id`, or `trip_id` entries to guarantee primary key uniqueness. |
| **Orphaned Records** | Trips and stop times referencing invalid routes or stops are automatically filtered out to preserve foreign key constraints. |
