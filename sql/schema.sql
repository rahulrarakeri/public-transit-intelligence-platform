-- ====================================================================
-- Transit Intelligence Platform - Multi-Feed Database Schema
-- Target Engine: PostgreSQL 14+
-- Database: transit_db
-- 
-- Architecture:
-- Supports multiple transit feeds (cities/agencies) coexisting within
-- a single database using composite keys (feed_id, id) and cascade rules.
-- ====================================================================

-- Drop dependent tables first to allow clean rebuilds
DROP TABLE IF EXISTS scoring_sensitivity CASCADE;
DROP TABLE IF EXISTS route_scores CASCADE;
DROP TABLE IF EXISTS headline_findings CASCADE;
DROP TABLE IF EXISTS data_quality_report CASCADE;
DROP TABLE IF EXISTS demand_recommendations CASCADE;
DROP TABLE IF EXISTS festival_calendar CASCADE;
DROP TABLE IF EXISTS stop_times CASCADE;
DROP TABLE IF EXISTS trips CASCADE;
DROP TABLE IF EXISTS calendar CASCADE;
DROP TABLE IF EXISTS stops CASCADE;
DROP TABLE IF EXISTS routes CASCADE;
DROP TABLE IF EXISTS feeds CASCADE;

-- 1. Feeds Registry: Tracks loaded transit feeds and agencies
CREATE TABLE feeds (
    feed_id VARCHAR(50) PRIMARY KEY,
    feed_name VARCHAR(100) NOT NULL,
    agency_name VARCHAR(150),
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100),
    country VARCHAR(50) DEFAULT 'India',
    timezone VARCHAR(50) DEFAULT 'Asia/Kolkata',
    gtfs_source VARCHAR(255),
    loaded_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    status VARCHAR(50) DEFAULT 'ACTIVE'
);

-- 2. Routes: Line definitions per feed
CREATE TABLE routes (
    feed_id VARCHAR(50) NOT NULL REFERENCES feeds(feed_id) ON DELETE CASCADE,
    route_id VARCHAR(50) NOT NULL,
    route_short_name VARCHAR(50) NOT NULL,
    route_long_name VARCHAR(255) NOT NULL,
    route_type INTEGER NOT NULL DEFAULT 3, -- GTFS standard: 3 = Bus, 1 = Metro, 2 = Rail
    PRIMARY KEY (feed_id, route_id)
);

-- 3. Stops: Physical station coordinates and zones per feed
CREATE TABLE stops (
    feed_id VARCHAR(50) NOT NULL REFERENCES feeds(feed_id) ON DELETE CASCADE,
    stop_id VARCHAR(50) NOT NULL,
    stop_name VARCHAR(255) NOT NULL,
    stop_lat DECIMAL(10, 6) NOT NULL,
    stop_lon DECIMAL(10, 6) NOT NULL,
    zone_id VARCHAR(50),
    PRIMARY KEY (feed_id, stop_id)
);

-- 4. Calendar: Service availability patterns per feed
CREATE TABLE calendar (
    feed_id VARCHAR(50) NOT NULL REFERENCES feeds(feed_id) ON DELETE CASCADE,
    service_id VARCHAR(50) NOT NULL,
    monday BOOLEAN NOT NULL DEFAULT TRUE,
    tuesday BOOLEAN NOT NULL DEFAULT TRUE,
    wednesday BOOLEAN NOT NULL DEFAULT TRUE,
    thursday BOOLEAN NOT NULL DEFAULT TRUE,
    friday BOOLEAN NOT NULL DEFAULT TRUE,
    saturday BOOLEAN NOT NULL DEFAULT TRUE,
    sunday BOOLEAN NOT NULL DEFAULT TRUE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    PRIMARY KEY (feed_id, service_id)
);

-- 5. Trips: Scheduled vehicle runs linked to routes and calendars
CREATE TABLE trips (
    feed_id VARCHAR(50) NOT NULL,
    trip_id VARCHAR(100) NOT NULL,
    route_id VARCHAR(50) NOT NULL,
    service_id VARCHAR(50) NOT NULL,
    direction_id INTEGER NOT NULL DEFAULT 0, -- 0 = Outbound, 1 = Inbound
    trip_headsign VARCHAR(255),
    PRIMARY KEY (feed_id, trip_id),
    FOREIGN KEY (feed_id, route_id) REFERENCES routes(feed_id, route_id) ON DELETE CASCADE,
    FOREIGN KEY (feed_id, service_id) REFERENCES calendar(feed_id, service_id) ON DELETE CASCADE
);

-- 6. Stop Times: Timetabled arrival/departure for each stop on a trip
-- Arrival and departure times use VARCHAR because GTFS supports overnight trips past 24:00:00
CREATE TABLE stop_times (
    feed_id VARCHAR(50) NOT NULL,
    trip_id VARCHAR(100) NOT NULL,
    stop_sequence INTEGER NOT NULL,
    arrival_time VARCHAR(20) NOT NULL,
    departure_time VARCHAR(20) NOT NULL,
    stop_id VARCHAR(50) NOT NULL,
    PRIMARY KEY (feed_id, trip_id, stop_sequence),
    FOREIGN KEY (feed_id, trip_id) REFERENCES trips(feed_id, trip_id) ON DELETE CASCADE,
    FOREIGN KEY (feed_id, stop_id) REFERENCES stops(feed_id, stop_id) ON DELETE CASCADE
);

-- 7. Festival Calendar: Regional events with scenario multipliers per feed
CREATE TABLE festival_calendar (
    festival_id SERIAL PRIMARY KEY,
    feed_id VARCHAR(50) NOT NULL REFERENCES feeds(feed_id) ON DELETE CASCADE,
    festival_name VARCHAR(100) NOT NULL,
    festival_date DATE NOT NULL,
    demand_multiplier DECIMAL(3, 1) NOT NULL,
    scenario VARCHAR(20) NOT NULL DEFAULT 'base',
    notes VARCHAR(255)
);

-- 8. Demand Recommendations: Calculated extra fleet requirements per feed & route
CREATE TABLE demand_recommendations (
    rec_id SERIAL PRIMARY KEY,
    feed_id VARCHAR(50) NOT NULL,
    scenario VARCHAR(20) NOT NULL DEFAULT 'base',
    route_id VARCHAR(50) NOT NULL,
    festival_date DATE NOT NULL,
    festival_name VARCHAR(100) NOT NULL,
    demand_multiplier DECIMAL(3, 1) NOT NULL DEFAULT 1.0,
    current_trip_count INTEGER NOT NULL,
    recommended_extra_buses INTEGER NOT NULL,
    priority_level VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (feed_id, route_id) REFERENCES routes(feed_id, route_id) ON DELETE CASCADE
);

-- 9. Route Prioritization Scores (RSGPI): Normalized multi-criteria prioritization
CREATE TABLE route_scores (
    feed_id VARCHAR(50) NOT NULL,
    route_id VARCHAR(50) NOT NULL,
    route_short_name VARCHAR(50) NOT NULL,
    route_long_name VARCHAR(255) NOT NULL,
    transfer_routes_connected INTEGER NOT NULL,
    off_peak_headway DECIMAL(6, 1) NOT NULL,
    weekend_gap_flag DECIMAL(3, 1) NOT NULL,
    stop_count INTEGER NOT NULL,
    norm_connectivity DECIMAL(5, 4) NOT NULL,
    norm_off_peak_gap DECIMAL(5, 4) NOT NULL,
    norm_weekend_deficit DECIMAL(5, 4) NOT NULL,
    norm_stop_density DECIMAL(5, 4) NOT NULL,
    composite_score DECIMAL(5, 2) NOT NULL,
    rank INTEGER NOT NULL,
    review_tier VARCHAR(50) NOT NULL,
    PRIMARY KEY (feed_id, route_id),
    FOREIGN KEY (feed_id, route_id) REFERENCES routes(feed_id, route_id) ON DELETE CASCADE
);

-- 10. Sensitivity Analysis Audit Record: Monte Carlo stability evaluation
CREATE TABLE scoring_sensitivity (
    id SERIAL PRIMARY KEY,
    feed_id VARCHAR(50) NOT NULL REFERENCES feeds(feed_id) ON DELETE CASCADE,
    iterations INTEGER NOT NULL,
    mean_spearman_rho DECIMAL(5, 3) NOT NULL,
    p5_spearman_rho DECIMAL(5, 3) NOT NULL,
    mean_top10_overlap DECIMAL(5, 2) NOT NULL,
    mean_bottom10_overlap DECIMAL(5, 2) NOT NULL,
    equal_weights_rho DECIMAL(5, 3) NOT NULL,
    evaluated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- 11. Headline Findings: Auto-computed executive headline metrics per feed
CREATE TABLE headline_findings (
    id SERIAL PRIMARY KEY,
    feed_id VARCHAR(50) NOT NULL REFERENCES feeds(feed_id) ON DELETE CASCADE,
    finding_id VARCHAR(50) NOT NULL,
    headline TEXT NOT NULL,
    key_metric VARCHAR(50) NOT NULL,
    sub_metric VARCHAR(50),
    details TEXT,
    business_implication TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    CONSTRAINT uq_feed_finding UNIQUE (feed_id, finding_id)
);

-- 12. Data Quality Report: Automated feed validation log per feed
CREATE TABLE data_quality_report (
    check_id SERIAL PRIMARY KEY,
    feed_id VARCHAR(50) NOT NULL REFERENCES feeds(feed_id) ON DELETE CASCADE,
    check_name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    issue_count INTEGER NOT NULL,
    details TEXT,
    audited_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- ====================================================================
-- Performance Indexes
-- ====================================================================
CREATE INDEX idx_routes_feed ON routes(feed_id);
CREATE INDEX idx_stops_feed ON stops(feed_id);
CREATE INDEX idx_calendar_feed ON calendar(feed_id);
CREATE INDEX idx_trips_feed_route ON trips(feed_id, route_id);
CREATE INDEX idx_trips_feed_service ON trips(feed_id, service_id);
CREATE INDEX idx_stop_times_feed_trip ON stop_times(feed_id, trip_id);
CREATE INDEX idx_stop_times_feed_stop ON stop_times(feed_id, stop_id);

CREATE INDEX idx_festival_calendar_feed ON festival_calendar(feed_id, scenario);
CREATE INDEX idx_demand_recommendations_feed ON demand_recommendations(feed_id, scenario);
CREATE INDEX idx_route_scores_feed_rank ON route_scores(feed_id, rank);
CREATE INDEX idx_headline_findings_feed ON headline_findings(feed_id);
CREATE INDEX idx_data_quality_feed ON data_quality_report(feed_id);
