-- ====================================================================
-- Transit Intelligence Platform - Headline Quantified Findings
-- Target Engine: PostgreSQL 14+
-- Database: transit_db
-- Description: Computes the 6 headline consulting findings directly in SQL.
-- Parameterized by :feed_id (e.g. 'chennai_mtc', 'sample_city').
-- ====================================================================

-- --------------------------------------------------------------------
-- 1. Peak vs. Off-Peak Supply Skew (Rush-Hour Compression)
-- Measures trip concentration in morning (07-10) and evening (17-20) peaks
-- --------------------------------------------------------------------
WITH trip_departures AS (
    SELECT t.trip_id, t.route_id,
           CAST(SPLIT_PART(MIN(st.departure_time), ':', 1) AS INTEGER) AS dep_hour
    FROM trips t
    JOIN stop_times st ON t.feed_id = st.feed_id AND t.trip_id = st.trip_id
    WHERE t.feed_id = :feed_id
    GROUP BY t.trip_id, t.route_id
)
SELECT 
    COUNT(*) AS total_trips,
    COUNT(CASE WHEN dep_hour BETWEEN 7 AND 9 OR dep_hour BETWEEN 17 AND 19 THEN 1 END) AS peak_trips,
    COUNT(CASE WHEN dep_hour NOT BETWEEN 7 AND 9 AND dep_hour NOT BETWEEN 17 AND 19 THEN 1 END) AS off_peak_trips,
    ROUND(COUNT(CASE WHEN dep_hour BETWEEN 7 AND 9 OR dep_hour BETWEEN 17 AND 19 THEN 1 END)::NUMERIC / NULLIF(COUNT(*), 0) * 100, 1) AS peak_share_pct,
    ROUND((COUNT(CASE WHEN dep_hour BETWEEN 7 AND 9 OR dep_hour BETWEEN 17 AND 19 THEN 1 END) / 6.0)::NUMERIC, 1) AS peak_hourly_departure_rate,
    ROUND((COUNT(CASE WHEN dep_hour NOT BETWEEN 7 AND 9 AND dep_hour NOT BETWEEN 17 AND 19 THEN 1 END) / 18.0)::NUMERIC, 1) AS off_peak_hourly_departure_rate,
    ROUND(((COUNT(CASE WHEN dep_hour BETWEEN 7 AND 9 OR dep_hour BETWEEN 17 AND 19 THEN 1 END) / 6.0) / 
           NULLIF((COUNT(CASE WHEN dep_hour NOT BETWEEN 7 AND 9 AND dep_hour NOT BETWEEN 17 AND 19 THEN 1 END) / 18.0), 0))::NUMERIC, 1) AS peak_to_offpeak_gap_ratio
FROM trip_departures;


-- --------------------------------------------------------------------
-- 2. Transfer Hub Concentration (Top 10 Super-Interchanges)
-- Measures the proportion of network-wide route connections handled by top 10 hubs
-- --------------------------------------------------------------------
WITH stop_connections AS (
    SELECT s.stop_id, s.stop_name,
           COUNT(DISTINCT r.route_id) AS routes_served,
           COUNT(DISTINCT t.trip_id) AS daily_trips_handled
    FROM stops s
    JOIN stop_times st ON s.feed_id = st.feed_id AND s.stop_id = st.stop_id
    JOIN trips t ON st.feed_id = t.feed_id AND st.trip_id = t.trip_id
    JOIN routes r ON t.feed_id = r.feed_id AND t.route_id = r.route_id
    WHERE s.feed_id = :feed_id
    GROUP BY s.stop_id, s.stop_name
),
ranked_stops AS (
    SELECT *,
           ROW_NUMBER() OVER (ORDER BY routes_served DESC, daily_trips_handled DESC) AS hub_rank,
           SUM(routes_served) OVER () AS network_total_connections
    FROM stop_connections
)
SELECT 
    COUNT(CASE WHEN hub_rank <= 10 THEN 1 END) AS top_hub_count,
    ROUND(COUNT(CASE WHEN hub_rank <= 10 THEN 1 END)::NUMERIC / NULLIF(COUNT(*)::NUMERIC, 0) * 100, 1) AS top_hubs_pct_of_stops,
    SUM(CASE WHEN hub_rank <= 10 THEN routes_served ELSE 0 END) AS top_10_hub_connections,
    MAX(network_total_connections) AS total_network_connections,
    ROUND(SUM(CASE WHEN hub_rank <= 10 THEN routes_served ELSE 0 END)::NUMERIC / NULLIF(MAX(network_total_connections), 0) * 100, 1) AS top_10_hub_connection_share_pct
FROM ranked_stops;


-- --------------------------------------------------------------------
-- 3. Weekend Service Availability Deserts
-- Identifies routes operating exclusively Monday-Friday with zero weekend service
-- --------------------------------------------------------------------
WITH route_weekends AS (
    SELECT r.route_id, r.route_short_name, r.route_long_name,
           BOOL_OR(c.saturday) AS has_sat,
           BOOL_OR(c.sunday) AS has_sun
    FROM routes r
    JOIN trips t ON r.feed_id = t.feed_id AND r.route_id = t.route_id
    JOIN calendar c ON t.feed_id = c.feed_id AND t.service_id = c.service_id
    WHERE r.feed_id = :feed_id
    GROUP BY r.route_id, r.route_short_name, r.route_long_name
)
SELECT 
    COUNT(*) AS total_routes,
    COUNT(CASE WHEN NOT COALESCE(has_sat, FALSE) AND NOT COALESCE(has_sun, FALSE) THEN 1 END) AS zero_weekend_routes_count,
    ROUND(COUNT(CASE WHEN NOT COALESCE(has_sat, FALSE) AND NOT COALESCE(has_sun, FALSE) THEN 1 END)::NUMERIC / NULLIF(COUNT(*)::NUMERIC, 0) * 100, 1) AS zero_weekend_share_pct,
    STRING_AGG(CASE WHEN NOT COALESCE(has_sat, FALSE) AND NOT COALESCE(has_sun, FALSE) THEN route_short_name END, ', ' ORDER BY route_short_name) AS affected_corridors
FROM route_weekends;


-- --------------------------------------------------------------------
-- 4. Off-Peak Headway Rigidity (Midday Service Intervals)
-- Calculates the proportion of corridors with off-peak headway >= 270 minutes (4.5 hours)
-- --------------------------------------------------------------------
WITH route_offpeak AS (
    SELECT t.route_id,
           COUNT(CASE WHEN CAST(SPLIT_PART(st.departure_time, ':', 1) AS INTEGER) NOT BETWEEN 7 AND 9 
                        AND CAST(SPLIT_PART(st.departure_time, ':', 1) AS INTEGER) NOT BETWEEN 17 AND 19 
                      THEN 1 END) AS off_peak_trips
    FROM trips t
    JOIN stop_times st ON t.feed_id = st.feed_id AND t.trip_id = st.trip_id
    WHERE t.feed_id = :feed_id
    GROUP BY t.route_id
)
SELECT 
    COUNT(*) AS total_routes,
    COUNT(CASE WHEN (18.0 * 60.0 / NULLIF(off_peak_trips, 0)) >= 270.0 OR off_peak_trips = 0 THEN 1 END) AS severe_offpeak_routes_count,
    ROUND(COUNT(CASE WHEN (18.0 * 60.0 / NULLIF(off_peak_trips, 0)) >= 270.0 OR off_peak_trips = 0 THEN 1 END)::NUMERIC / NULLIF(COUNT(*)::NUMERIC, 0) * 100, 1) AS severe_offpeak_share_pct
FROM route_offpeak;


-- --------------------------------------------------------------------
-- 5. Flat Corridor Allocation Inelasticity
-- Tests whether daily trip counts correlate with network transfer connections
-- --------------------------------------------------------------------
WITH route_stops_distinct AS (
    SELECT DISTINCT t.route_id, st.stop_id
    FROM trips t
    JOIN stop_times st ON t.feed_id = st.feed_id AND t.trip_id = st.trip_id
    WHERE t.feed_id = :feed_id
),
route_summary AS (
    SELECT r.route_id,
           COUNT(DISTINCT t.trip_id) AS trips_per_day,
           COUNT(DISTINCT rs2.route_id) AS connected_routes
    FROM routes r
    LEFT JOIN trips t ON r.feed_id = t.feed_id AND r.route_id = t.route_id
    LEFT JOIN route_stops_distinct rs1 ON r.route_id = rs1.route_id
    LEFT JOIN route_stops_distinct rs2 ON rs1.stop_id = rs2.stop_id AND rs1.route_id != rs2.route_id
    WHERE r.feed_id = :feed_id
    GROUP BY r.route_id
)
SELECT 
    MIN(trips_per_day) AS min_daily_trips,
    MAX(trips_per_day) AS max_daily_trips,
    AVG(trips_per_day) AS avg_daily_trips,
    MIN(connected_routes) AS min_connected_routes,
    MAX(connected_routes) AS max_connected_routes,
    ROUND(MAX(connected_routes)::NUMERIC / NULLIF(MIN(connected_routes), 0), 1) AS connectivity_variance_ratio
FROM route_summary;


-- --------------------------------------------------------------------
-- 6. Festival Demand Surge Fleet Extra Requirements
-- Computes the incremental bus runs required across festive scenarios
-- --------------------------------------------------------------------
SELECT 
    scenario,
    COUNT(DISTINCT festival_name) AS festival_count,
    SUM(recommended_extra_buses) AS total_extra_bus_runs_projected,
    ROUND(AVG(recommended_extra_buses)::NUMERIC, 1) AS avg_extra_buses_per_route_festival
FROM demand_recommendations
WHERE feed_id = :feed_id
GROUP BY scenario
ORDER BY CASE scenario WHEN 'low' THEN 1 WHEN 'base' THEN 2 WHEN 'high' THEN 3 ELSE 4 END;
