# Entity Relationship Diagram (ERD) & Data Schema

The platform maintains a relational PostgreSQL schema partitioned into **GTFS Core Entities**, **Analytical Demand Models**, and **Auditing & Decision Support Tables**.

---

## Relational Architecture Diagram

```mermaid
erDiagram
    ROUTES ||--o{ TRIPS : "operates"
    CALENDAR ||--o{ TRIPS : "schedules"
    TRIPS ||--|{ STOP_TIMES : "sequences"
    STOPS ||--o{ STOP_TIMES : "serves"
    ROUTES ||--o{ DEMAND_RECOMMENDATIONS : "projects"
    ROUTES ||--|| ROUTE_SCORES : "evaluates"
    FESTIVAL_CALENDAR ||--o{ DEMAND_RECOMMENDATIONS : "multiplies"

    ROUTES {
        varchar route_id PK
        varchar route_short_name
        varchar route_long_name
        integer route_type
    }

    STOPS {
        varchar stop_id PK
        varchar stop_name
        decimal stop_lat
        decimal stop_lon
        varchar zone_id
    }

    CALENDAR {
        varchar service_id PK
        boolean monday
        boolean tuesday
        boolean wednesday
        boolean thursday
        boolean friday
        boolean saturday
        boolean sunday
        date start_date
        date end_date
    }

    TRIPS {
        varchar trip_id PK
        varchar route_id FK
        varchar service_id FK
        integer direction_id
        varchar trip_headsign
    }

    STOP_TIMES {
        varchar trip_id PK, FK
        integer stop_sequence PK
        varchar arrival_time
        varchar departure_time
        varchar stop_id FK
    }

    FESTIVAL_CALENDAR {
        integer festival_id PK
        varchar festival_name
        date festival_date
        decimal demand_multiplier
        varchar scenario
        varchar notes
    }

    DEMAND_RECOMMENDATIONS {
        integer rec_id PK
        varchar scenario
        varchar route_id FK
        date festival_date
        varchar festival_name
        decimal demand_multiplier
        integer current_trip_count
        integer recommended_extra_buses
        varchar priority_level
        timestamp created_at
    }

    ROUTE_SCORES {
        varchar route_id PK, FK
        varchar route_short_name
        varchar route_long_name
        integer transfer_routes_connected
        decimal off_peak_headway
        decimal weekend_gap_flag
        integer stop_count
        decimal norm_connectivity
        decimal norm_off_peak_gap
        decimal norm_weekend_deficit
        decimal norm_stop_density
        decimal composite_score
        integer rank
        varchar review_tier
    }

    HEADLINE_FINDINGS {
        integer id PK
        varchar finding_id UK
        text headline
        varchar key_metric
        varchar sub_metric
        text details
        text business_implication
        timestamp created_at
    }

    DATA_QUALITY_REPORT {
        integer check_id PK
        varchar check_name
        varchar category
        varchar status
        integer issue_count
        text details
        timestamp audited_at
    }

    SCORING_SENSITIVITY {
        integer id PK
        integer iterations
        decimal mean_spearman_rho
        decimal p5_spearman_rho
        decimal mean_top10_overlap
        decimal mean_bottom10_overlap
        decimal equal_weights_rho
        timestamp evaluated_at
    }
```

---

## Schema Component Descriptions

### 1. GTFS Ingestion Core
- **`routes`**: Bus line identifiers, short line numbers, and descriptive terminal-to-terminal names.
- **`stops`**: Physical boarding points with geographic GPS latitude and longitude coordinates.
- **`calendar`**: Day-of-week boolean availability masks (`monday`...`sunday`) and date ranges.
- **`trips`**: Individual vehicle runs linked to routes and service schedules.
- **`stop_times`**: Chronological arrival and departure times at each stop sequence along a trip. Timestamps stored as `VARCHAR(20)` to natively support GTFS overnight schedules ($\ge \text{24:00:00}$).

### 2. Analytical Decision Support
- **`festival_calendar`**: Evaluates 15 Indian cultural and regional events across Low, Base, and High scenario multipliers.
- **`demand_recommendations`**: Pre-computed corridor extra vehicle requirements across all festivals and scenarios.
- **`route_scores`**: Multi-criteria Route Prioritization Index (RSGPI) synthesizing normalized transfer connectivity, off-peak headways, weekend availability, and stop counts.
- **`scoring_sensitivity`**: Audit log of 500-iteration Monte Carlo sensitivity analysis measuring Spearman rank correlation and Top-10 stability.
- **`headline_findings`**: Auto-populated quantified executive consulting metrics.
- **`data_quality_report`**: Feed verification log recording nulls, orphans, duplicate records, and spatial validity.
