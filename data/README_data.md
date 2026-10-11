# Transit Data Documentation

## Overview

This directory contains the General Transit Feed Specification (GTFS) data archive and data documentation for the **Public Transit Intelligence Platform**. The primary transit schedule source is archived in `data/gtfs_feed.zip` based on the metropolitan bus network in Chennai.

---

## GTFS Feed Specification (`data/gtfs_feed.zip`)

The archive contains standard GTFS specification CSV files defining network infrastructure and timetables:

| File Name | Description | Key Fields |
| :--- | :--- | :--- |
| `routes.txt` | Transit route identifiers, line numbers, and corridor names | `route_id`, `route_short_name`, `route_long_name`, `route_type` |
| `stops.txt` | Physical bus stops and terminal locations with GPS coordinates | `stop_id`, `stop_name`, `stop_lat`, `stop_lon`, `zone_id` |
| `calendar.txt` | Service schedules by day of the week and effective date ranges | `service_id`, `monday`...`sunday`, `start_date`, `end_date` |
| `trips.txt` | Scheduled vehicle journeys associated with routes and service profiles | `trip_id`, `route_id`, `service_id`, `direction_id`, `trip_headsign` |
| `stop_times.txt` | Scheduled arrival and departure timetables at each stop sequence | `trip_id`, `stop_sequence`, `arrival_time`, `departure_time`, `stop_id` |

---

## Operational & Spatial Parameters

- **Geographic Bounding Box:**
  - Latitude: $12.90^\circ\text{N}$ to $13.20^\circ\text{N}$
  - Longitude: $80.10^\circ\text{E}$ to $80.30^\circ\text{E}$
- **Key Interchanges & Terminals:**
  - Koyambedu Bus Terminus (CMBT), Tambaram, Broadway, Central Railway Station, Guindy, T Nagar, Adyar, Velachery, Sholinganallur, and Poonamallee.
- **Service Time Bands:**
  - **Morning Peak:** 07:00 to 10:00 (High-frequency commuter inbound movement)
  - **Evening Peak:** 17:00 to 20:00 (High-frequency outbound dispersal)
  - **Off-Peak:** 10:00 to 17:00 and 20:00 to 23:00 (Standard interval spacing)
  - **Service Types:** Daily schedules (`c_daily`), weekday commuter lines (`c_weekday`), and weekend-only lines (`c_weekend`).

---

## Festival Demand Multipliers

Regional festivals significantly increase passenger demand at major transit hubs. The system tracks 15 major Indian festive events across 2025–2026 using estimated surge multipliers to compute supplementary bus requirements:

| Festival Name | Date | Multiplier | Operational Impact |
| :--- | :--- | :---: | :--- |
| **Pongal** | 2025-01-14 | 2.2× | Major harvest festival, outbound rush at CMBT and Tambaram |
| **Republic Day** | 2025-01-26 | 1.8× | Coastal holiday traffic towards Marina Beach |
| **Holi** | 2025-03-14 | 1.6× | Community celebrations and retail travel |
| **Eid ul-Fitr** | 2025-03-30 | 2.0× | High demand around Triplicane & George Town bazaars |
| **Good Friday** | 2025-04-18 | 1.4× | Church congregations in Santhome & Besant Nagar |
| **Independence Day**| 2025-08-15 | 1.9× | Public holiday leisure transit |
| **Ganesh Chaturthi**| 2025-08-27 | 2.2× | Immersion procession corridors towards the coast |
| **Navaratri** | 2025-09-22 | 1.7× | Evening temple circuits in Mylapore & Triplicane |
| **Dussehra** | 2025-10-02 | 2.0× | Retail shopping and holiday travel |
| **Diwali** | 2025-10-20 | 2.5× | Peak retail influx in T Nagar and heavy terminus departures |
| **Diwali Day 2** | 2025-10-21 | 2.3× | Family visits and return citywide travel |
| **Christmas** | 2025-12-25 | 1.8× | Church services and evening leisure travel on ECR |
| **New Year Eve** | 2025-12-31 | 2.1× | Late-night crowds along coastal corridors |
| **New Year Day** | 2026-01-01 | 1.9× | Outings to parks, zoo, and leisure hubs |
| **Pongal 2026** | 2026-01-14 | 2.2× | Annual harvest festival transit peak |

---

## Data Pipeline Execution

To ingest the GTFS feed into PostgreSQL:

```bash
python ingestion/load_gtfs.py
```

### Mock Data Generation (For Testing)

To generate a synthetic GTFS feed for offline testing:

```bash
python data/generate_sample_data.py --routes 50 --stops 150 --trips 500 --output-zip data/synthetic_sample_feed.zip
```
