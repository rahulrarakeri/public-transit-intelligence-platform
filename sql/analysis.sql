-- ====================================================================
-- Transit Intelligence Platform - Parameterized Analytical SQL Suite
-- Target Engine: PostgreSQL 14+
-- Database: transit_db
-- 
-- Architecture:
-- Fully parameterized for multi-feed analytics. Accepts :feed_id
-- and configurable operating parameters (peak windows, thresholds, scenarios).
-- ====================================================================

-- --------------------------------------------------------------------
-- 1. Route Stop Coverage Ranking
-- Business Hypothesis: Spatial Extent & Supply Allocation (Hypothesis 4)
-- Parameters: :feed_id (e.g. 'chennai_mtc', 'sample_city')
-- --------------------------------------------------------------------
WITH route_stops AS (
    SELECT 
        r.route_id,
        r.route_short_name,
        r.route_long_name,
        COUNT(DISTINCT st.stop_id) AS total_unique_stops
    FROM routes r
    JOIN trips t ON r.feed_id = t.feed_id AND r.route_id = t.route_id
    JOIN stop_times st ON t.feed_id = st.feed_id AND t.trip_id = st.trip_id
    WHERE r.feed_id = :feed_id
    GROUP BY r.route_id, r.route_short_name, r.route_long_name
)
SELECT 
    route_id,
    route_short_name,
    route_long_name,
    total_unique_stops,
    RANK() OVER (ORDER BY total_unique_stops DESC) AS stop_coverage_rank
FROM route_stops
ORDER BY stop_coverage_rank ASC, route_short_name ASC;


-- --------------------------------------------------------------------
-- 2. Top Interchange Transfer Hubs
-- Business Hypothesis: Hub Concentration & Systemic Vulnerability (Hypothesis 1)
-- Parameters: :feed_id (e.g. 'chennai_mtc'), :top_n (e.g. 10)
-- --------------------------------------------------------------------
WITH stop_connectivity AS (
    SELECT 
        s.stop_id,
        s.stop_name,
        s.stop_lat,
        s.stop_lon,
        COUNT(DISTINCT r.route_id) AS distinct_routes_served,
        COUNT(DISTINCT t.trip_id) AS total_daily_trips_handled
    FROM stops s
    JOIN stop_times st ON s.feed_id = st.feed_id AND s.stop_id = st.stop_id
    JOIN trips t ON st.feed_id = t.feed_id AND st.trip_id = t.trip_id
    JOIN routes r ON t.feed_id = r.feed_id AND t.route_id = r.route_id
    WHERE s.feed_id = :feed_id
    GROUP BY s.stop_id, s.stop_name, s.stop_lat, s.stop_lon
),
ranked_hubs AS (
    SELECT 
        stop_id,
        stop_name,
        stop_lat,
        stop_lon,
        distinct_routes_served,
        total_daily_trips_handled,
        DENSE_RANK() OVER (
            ORDER BY distinct_routes_served DESC, total_daily_trips_handled DESC
        ) AS hub_rank
    FROM stop_connectivity
)
SELECT 
    hub_rank,
    stop_id,
    stop_name,
    distinct_routes_served,
    total_daily_trips_handled
FROM ranked_hubs
WHERE hub_rank <= COALESCE(:top_n, 10)
ORDER BY hub_rank ASC;


-- --------------------------------------------------------------------
-- 3. Peak vs. Off-Peak Trip Distribution by Route
-- Business Hypothesis: Temporal Supply Distortion / Rush-Hour Skew (Hypothesis 2)
-- Parameters: :feed_id, :morning_start, :morning_end, :evening_start, :evening_end
-- --------------------------------------------------------------------
WITH trip_first_departures AS (
    SELECT 
        t.trip_id,
        t.route_id,
        MIN(st.departure_time) AS initial_departure_time
    FROM trips t
    JOIN stop_times st ON t.feed_id = st.feed_id AND t.trip_id = st.trip_id
    WHERE t.feed_id = :feed_id
    GROUP BY t.trip_id, t.route_id
),
classified_trips AS (
    SELECT 
        r.route_id,
        r.route_short_name,
        r.route_long_name,
        tfd.trip_id,
        CAST(SPLIT_PART(tfd.initial_departure_time, ':', 1) AS INTEGER) AS dep_hour,
        CASE 
            WHEN CAST(SPLIT_PART(tfd.initial_departure_time, ':', 1) AS INTEGER) 
                 BETWEEN COALESCE(:morning_start, 7) AND COALESCE(:morning_end, 9) THEN 'Morning Peak'
            WHEN CAST(SPLIT_PART(tfd.initial_departure_time, ':', 1) AS INTEGER) 
                 BETWEEN COALESCE(:evening_start, 17) AND COALESCE(:evening_end, 19) THEN 'Evening Peak'
            ELSE 'Off-Peak'
        END AS time_band
    FROM trip_first_departures tfd
    JOIN routes r ON r.feed_id = :feed_id AND tfd.route_id = r.route_id
)
SELECT 
    route_id,
    route_short_name,
    route_long_name,
    COUNT(trip_id) AS total_trips,
    COUNT(CASE WHEN time_band = 'Morning Peak' THEN 1 END) AS morning_peak_trips,
    COUNT(CASE WHEN time_band = 'Evening Peak' THEN 1 END) AS evening_peak_trips,
    COUNT(CASE WHEN time_band = 'Off-Peak' THEN 1 END) AS off_peak_trips,
    ROUND(
        (COUNT(CASE WHEN time_band IN ('Morning Peak', 'Evening Peak') THEN 1 END)::NUMERIC 
         / NULLIF(COUNT(trip_id), 0)) * 100, 
        2
    ) AS peak_trip_percentage
FROM classified_trips
GROUP BY route_id, route_short_name, route_long_name
ORDER BY total_trips DESC;


-- --------------------------------------------------------------------
-- 4. Headway Service Evaluation (Supply Gap Screening)
-- Business Hypothesis: Baseline Service Intervals & Supply Deficit (Hypotheses 2 & 4)
-- Parameters: :feed_id, :high_headway_min (e.g. 45.0), :mod_headway_min (e.g. 30.0)
-- --------------------------------------------------------------------
WITH route_headways AS (
    SELECT 
        r.route_id,
        r.route_short_name,
        r.route_long_name,
        COUNT(t.trip_id) AS daily_trip_count,
        ROUND(1440.0 / NULLIF(COUNT(t.trip_id), 0), 1) AS avg_headway_minutes
    FROM routes r
    LEFT JOIN trips t ON r.feed_id = t.feed_id AND r.route_id = t.route_id
    WHERE r.feed_id = :feed_id
    GROUP BY r.route_id, r.route_short_name, r.route_long_name
),
service_level_evaluation AS (
    SELECT 
        route_id,
        route_short_name,
        route_long_name,
        daily_trip_count,
        avg_headway_minutes,
        CASE 
            WHEN avg_headway_minutes > COALESCE(:high_headway_min, 45.0) THEN 'HIGH HEADWAY (>45 min)'
            WHEN avg_headway_minutes > COALESCE(:mod_headway_min, 30.0) THEN 'MODERATE HEADWAY (30-45 min)'
            WHEN avg_headway_minutes BETWEEN 15.0 AND COALESCE(:mod_headway_min, 30.0) THEN 'STANDARD HEADWAY (15-30 min)'
            ELSE 'HIGH FREQUENCY (<15 min)'
        END AS service_classification
    FROM route_headways
)
SELECT 
    route_id,
    route_short_name,
    route_long_name,
    daily_trip_count,
    avg_headway_minutes,
    service_classification
FROM service_level_evaluation
ORDER BY avg_headway_minutes DESC;


-- --------------------------------------------------------------------
-- 5. Festival Surge Fleet Allocation & Dispatch Prioritization
-- Business Hypothesis: Festival Holiday Surge Capacity Deficit (Hypothesis 5)
-- Parameters: :feed_id, :scenario ('base', 'low', 'high')
-- --------------------------------------------------------------------
SELECT 
    f.festival_name,
    f.festival_date,
    f.demand_multiplier,
    dr.route_id,
    r.route_short_name,
    r.route_long_name,
    dr.current_trip_count,
    dr.recommended_extra_buses,
    dr.priority_level
FROM demand_recommendations dr
JOIN routes r ON dr.feed_id = r.feed_id AND dr.route_id = r.route_id
JOIN festival_calendar f ON dr.feed_id = f.feed_id 
                         AND dr.festival_name = f.festival_name 
                         AND dr.festival_date = f.festival_date
                         AND dr.scenario = f.scenario
WHERE dr.feed_id = :feed_id 
  AND dr.scenario = COALESCE(:scenario, 'base')
ORDER BY f.festival_date ASC, dr.recommended_extra_buses DESC;


-- --------------------------------------------------------------------
-- 6. Weekend Service Coverage Gaps
-- Business Hypothesis: Weekend Commuter Accessibility Blind Spot (Hypothesis 3)
-- Parameters: :feed_id
-- --------------------------------------------------------------------
WITH route_calendar_summary AS (
    SELECT 
        r.route_id,
        r.route_short_name,
        r.route_long_name,
        BOOL_OR(c.saturday) AS has_saturday_service,
        BOOL_OR(c.sunday) AS has_sunday_service,
        COUNT(t.trip_id) AS total_weekday_trips
    FROM routes r
    JOIN trips t ON r.feed_id = t.feed_id AND r.route_id = t.route_id
    JOIN calendar c ON t.feed_id = c.feed_id AND t.service_id = c.service_id
    WHERE r.feed_id = :feed_id
    GROUP BY r.route_id, r.route_short_name, r.route_long_name
)
SELECT 
    route_id,
    route_short_name,
    route_long_name,
    total_weekday_trips,
    COALESCE(has_saturday_service, FALSE) AS has_saturday_service,
    COALESCE(has_sunday_service, FALSE) AS has_sunday_service,
    CASE 
        WHEN NOT COALESCE(has_saturday_service, FALSE) AND NOT COALESCE(has_sunday_service, FALSE) THEN 'NO WEEKEND SERVICE'
        WHEN NOT COALESCE(has_saturday_service, FALSE) THEN 'NO SATURDAY SERVICE'
        WHEN NOT COALESCE(has_sunday_service, FALSE) THEN 'NO SUNDAY SERVICE'
        ELSE 'FULL WEEKEND SERVICE'
    END AS weekend_status
FROM route_calendar_summary
WHERE COALESCE(has_saturday_service, FALSE) = FALSE 
   OR COALESCE(has_sunday_service, FALSE) = FALSE
ORDER BY total_weekday_trips DESC;


-- --------------------------------------------------------------------
-- 7. Multi-Criteria Route Prioritization Index (SQL Mirror of RSGPI)
-- Business Hypothesis: Synthesis & Supply Review Prioritization
-- Parameters: :feed_id
-- --------------------------------------------------------------------
WITH route_metrics AS (
    SELECT 
        r.route_id,
        r.route_short_name,
        r.route_long_name,
        COUNT(DISTINCT st.stop_id) AS stop_count,
        COUNT(DISTINCT t.trip_id) AS daily_trips
    FROM routes r
    JOIN trips t ON r.feed_id = t.feed_id AND r.route_id = t.route_id
    JOIN stop_times st ON t.feed_id = st.feed_id AND t.trip_id = st.trip_id
    WHERE r.feed_id = :feed_id
    GROUP BY r.route_id, r.route_short_name, r.route_long_name
),
route_stops_distinct AS (
    SELECT DISTINCT t.route_id, st.stop_id
    FROM trips t
    JOIN stop_times st ON t.feed_id = st.feed_id AND t.trip_id = st.trip_id
    WHERE t.feed_id = :feed_id
),
route_transfers AS (
    SELECT 
        rs1.route_id,
        COUNT(DISTINCT rs2.route_id) AS transfer_connections
    FROM route_stops_distinct rs1
    JOIN route_stops_distinct rs2 ON rs1.stop_id = rs2.stop_id AND rs1.route_id != rs2.route_id
    GROUP BY rs1.route_id
),
percentile_metrics AS (
    SELECT 
        rm.route_id,
        rm.route_short_name,
        rm.route_long_name,
        rm.stop_count,
        rm.daily_trips,
        COALESCE(rt.transfer_connections, 0) AS transfer_connections,
        PERCENT_RANK() OVER (ORDER BY COALESCE(rt.transfer_connections, 0) ASC) AS connectivity_pct,
        PERCENT_RANK() OVER (ORDER BY rm.stop_count ASC) AS stop_pct
    FROM route_metrics rm
    LEFT JOIN route_transfers rt ON rm.route_id = rt.route_id
)
SELECT 
    route_id,
    route_short_name,
    route_long_name,
    transfer_connections,
    stop_count,
    daily_trips,
    ROUND((((0.60 * connectivity_pct) + (0.40 * stop_pct)) * 100)::NUMERIC, 2) AS sql_priority_score,
    CASE 
        WHEN ((0.60 * connectivity_pct) + (0.40 * stop_pct)) * 100 >= 70 THEN 'Tier 1 Priority Review'
        WHEN ((0.60 * connectivity_pct) + (0.40 * stop_pct)) * 100 >= 40 THEN 'Tier 2 Moderate Review'
        ELSE 'Tier 3 Stable Corridor'
    END AS review_tier
FROM percentile_metrics
ORDER BY sql_priority_score DESC;


-- --------------------------------------------------------------------
-- 8. Rolling Moving Average of Trip Frequencies
-- Business Hypothesis: Timetable Volatility Smoothing
-- Parameters: :feed_id
-- --------------------------------------------------------------------
WITH route_frequencies AS (
    SELECT 
        r.route_id,
        r.route_short_name,
        r.route_long_name,
        COUNT(t.trip_id) AS trip_count
    FROM routes r
    LEFT JOIN trips t ON r.feed_id = t.feed_id AND r.route_id = t.route_id
    WHERE r.feed_id = :feed_id
    GROUP BY r.route_id, r.route_short_name, r.route_long_name
)
SELECT 
    route_id,
    route_short_name,
    route_long_name,
    trip_count,
    ROUND(
        AVG(trip_count) OVER (
            ORDER BY trip_count DESC
            ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING
        ), 
        2
    ) AS rolling_avg_5_routes,
    ROUND(
        AVG(trip_count) OVER (
            ORDER BY trip_count DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ), 
        2
    ) AS cumulative_avg_trips
FROM route_frequencies
ORDER BY trip_count DESC;
