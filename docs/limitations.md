# Limitations, Data Quality & Validation Roadmap

A critical skill in management consulting is understanding the boundaries of your data. This document outlines the structural limitations of the current dataset, explains why specific claims cannot be made from GTFS alone, and specifies the empirical data sources required to address each gap.

---

## 1. Core Data Limitations

### Limitation 1: Scheduled Supply vs. Realized Operations
- **Current Data:** Static GTFS timetable files (`routes.txt`, `stops.txt`, `calendar.txt`, `trips.txt`, `stop_times.txt`).
- **Constraint:** GTFS represents the *intended schedule*, not what happens on the road. It does not reflect:
  - Traffic congestion and corridor-level speed variations
  - Vehicle breakdowns, driver absenteeism, or cancelled trips
  - Bus bunching and dynamic headway variability
- **Consulting Implication:** We cannot measure *reliability* or *on-time performance (OTP)* without real-world operational logs. All findings are strictly **supply-side timetable evaluations**.

---

### Limitation 2: Absence of Demand & Ridership Telemetry
- **Current Data:** Timetable frequencies and stop sequences.
- **Constraint:** The dataset contains **zero passenger boarding, alighting, or load factor data**.
  - We do *not* know how many passengers board at each stop.
  - We do *not* know passenger crowding levels, pass-ups, or unserved demand.
- **Consulting Rule:** **Never claim a route "needs more buses" based on GTFS alone.** We can only classify routes as having *supply-side service gaps* or identify corridors that are *candidates for operational review*.

---

### Limitation 3: Festival Surge Multipliers are Exogenous Assumptions
- **Current Data:** Festival surge multipliers ranging from 1.4× to 2.5× in `config/festival_config.json`.
- **Constraint:** Multipliers are **analytical planning assumptions** grounded in regional holiday travel patterns, **not** empirically measured farebox surges.
- **Mitigation:**
  - Explicitly labeled in code and configs as `ASSUMPTION - not derived from ridership data`.
  - Implemented scenario toggling (**Low, Base, High**) to test sensitivity to multiplier variation.

---

### Limitation 4: Uniform Scheduled Trip Volume in Feed
- **Current Data:** In the provided GTFS feed, all 50 routes contain exactly 10 scheduled daily trips (500 trips total).
- **Constraint:** While routes vary widely in spatial stop count (20 stops), transfer connections (7 to 18 lines), and temporal peak concentration (40% to 100%), the flat 10-trip schedule creates identical base daily headway (144.0 min).
- **Mitigation:** Our analysis isolates **off-peak headways**, **transfer connectivity**, and **calendar profiles** where empirical variance actually exists.

---

## 2. Additional Telemetry Required for Production Implementation

To upgrade this proof-of-concept into a full transit authority decision platform, four complementary data streams must be integrated:

```text
┌───────────────────────────────┐     ┌───────────────────────────────┐
│         Static GTFS           │     │          GTFS-Realtime        │
│   (Timetable Supply Truth)    │     │      (GPS Vehicle Positions)  │
└───────────────┬───────────────┘     └───────────────┬───────────────┘
                │                                     │
                ▼                                     ▼
        ┌─────────────────────────────────────────────────────┐
        │        Transit Analytics Integration Engine         │
        └─────────────────────────┬───────────────────────────┘
                                  │
         ┌────────────────────────┴────────────────────────┐
         ▼                                                 ▼
┌───────────────────────────────┐         ┌───────────────────────────────┐
│     Automated Fare (AFC/ETM)  │         │      Origin-Destination (OD)  │
│  (Passenger Boarding Demand)  │         │     (Cellular / App Traces)   │
└───────────────────────────────┘         └───────────────────────────────┘
```

| Required Data Source | Data Attributes | Analytical Gap Solved |
| :--- | :--- | :--- |
| **GTFS-Realtime (GTFS-RT)** | Vehicle position (lat/lon), trip updates, timestamps, vehicle delay (seconds) | Measures actual on-time performance (OTP), schedule adherence, and vehicle bunching. |
| **Electronic Ticketing Machines (ETM)** | Route, bus ID, timestamp, stop ID, fare stage, passenger count | Ground truth hourly ridership, corridor revenue, and passenger load factor per trip. |
| **Automated Passenger Counters (APC)** | Infrared door sensors: boarding and alighting counts per door | Precise crowding metrics, passenger volume profiles, and capacity bottlenecks. |
| **Origin-Destination (OD) Travel Matrices** | Trip start zone, destination zone, interchange transfer point, travel time | Validates route alignment against commuter travel desire lines; guides route restructuring. |

---

## 3. Automated Feed Quality Audit Results

Our data quality engine ([`src/data_quality.py`](file:///Users/rahularakeri/Public%20Transit%20Intelligence%20Platform/src/data_quality.py)) systematically audits feed integrity across 7 criteria:

```text
================================================================================
           GTFS DATA QUALITY & INTEGRITY AUDIT RESULTS
================================================================================
Check Name                       | Category             | Status   | Issues
--------------------------------------------------------------------------------
Null Critical Fields             | Completeness         | PASS     | 0     
Duplicate Primary Keys           | Uniqueness           | PASS     | 0     
Referential Integrity            | Consistency          | PASS     | 0     
Geospatial Bounding Box          | Validity             | PASS     | 0     
GTFS Overnight Timestamps (>=24h)| Validity (GTFS Spec) | INFO     | 0     
Dwell Time Logic                 | Temporal Consistency | PASS     | 0     
Unserved Network Assets          | Coverage             | INFO     | 3     
================================================================================
```

### Key Integrity Findings:
1. **Referential Integrity:** 100% verified. Zero orphaned foreign keys between `stop_times -> trips` and `trips -> routes`.
2. **Geospatial Integrity:** All 150 stops fall strictly within metropolitan Chennai bounds ($12.91^\circ\text{N} - 13.15^\circ\text{N}$, $80.12^\circ\text{E} - 80.28^\circ\text{E}$).
3. **Unserved Assets:** 3 stops out of 150 are unserved in the scheduled timetable (`STOP_148`, `STOP_149`, `STOP_150`), representing dormant or planned stops.
