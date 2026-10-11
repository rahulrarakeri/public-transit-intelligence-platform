"""
Route Supply Gap Priority Index (RSGPI) & Sensitivity Analysis

Computes a 0-100 priority score for bus corridors by combining:
- Network transfer connectivity
- Off-peak service headway
- Weekend service deficits
- Stop density

Also runs a 500-iteration Monte Carlo simulation (+/- 20% weight jitter)
to verify that the resulting route ranking is stable and not sensitive to arbitrary weights.
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Tuple, List, Optional
import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config

logger = logging.getLogger("analytics.scoring")


def compute_spearman_rho(s1: pd.Series, s2: pd.Series) -> float:
    # Instead of importing scipy just for spearmanr, we can rank the series
    # and compute standard Pearson correlation. It gives the exact same result
    # and keeps our dependencies lightweight.
    r1 = s1.rank()
    r2 = s2.rank()
    val = r1.corr(r2, method="pearson")
    return float(val) if not pd.isna(val) else 1.0


def min_max_normalize(series: pd.Series) -> pd.Series:
    """Normalizes a numeric series to [0.0, 1.0] using Min-Max scaling."""
    s_min = series.min()
    s_max = series.max()
    if pd.isna(s_min) or pd.isna(s_max) or s_max == s_min:
        return pd.Series(0.5, index=series.index)
    return (series - s_min) / (s_max - s_min)


def fetch_route_features(
    engine: Engine,
    feed_id: str = "chennai_mtc",
    feed_config: Optional[Dict[str, Any]] = None
) -> pd.DataFrame:
    """
    Extracts route-level supply and connectivity features from transit_db for a specific feed:
    - transfer_routes_connected: Count of other distinct lines intersecting this corridor
    - off_peak_headway: Off-peak headway in minutes ((off_peak_hours * 60) / off_peak_trips)
    - weekend_gap_flag: 1 if line shuts down on weekends, 0 otherwise
    - stop_count: Number of unique physical stops served by the route
    """
    peak_cfg = (feed_config or {}).get("peak_hours", {
        "morning_peak": [7, 8, 9],
        "evening_peak": [17, 18, 19]
    })
    morning_hours = list(peak_cfg.get("morning_peak", [7, 8, 9]))
    evening_hours = list(peak_cfg.get("evening_peak", [17, 18, 19]))
    all_peak_hours = set(morning_hours + evening_hours)
    off_peak_hours_count = max(1, 24 - len(all_peak_hours))

    # Construct SQL with parameterized peak hours
    query = """
        WITH route_base AS (
            SELECT 
                r.route_id,
                r.route_short_name,
                r.route_long_name,
                COUNT(DISTINCT st.stop_id) AS stop_count
            FROM routes r
            JOIN trips t ON r.feed_id = t.feed_id AND r.route_id = t.route_id
            JOIN stop_times st ON t.feed_id = st.feed_id AND t.trip_id = st.trip_id
            WHERE r.feed_id = :fid
            GROUP BY r.route_id, r.route_short_name, r.route_long_name
        ),
        route_stops AS (
            SELECT DISTINCT t.route_id, st.stop_id
            FROM trips t
            JOIN stop_times st ON t.feed_id = st.feed_id AND t.trip_id = st.trip_id
            WHERE t.feed_id = :fid
        ),
        route_transfers AS (
            SELECT 
                rs1.route_id,
                COUNT(DISTINCT rs2.route_id) AS transfer_routes_connected
            FROM route_stops rs1
            JOIN route_stops rs2 ON rs1.stop_id = rs2.stop_id AND rs1.route_id != rs2.route_id
            GROUP BY rs1.route_id
        ),
        route_temporal AS (
            SELECT 
                t.route_id,
                COUNT(DISTINCT t.trip_id) AS total_trips,
                MIN(CAST(SPLIT_PART(st.departure_time, ':', 1) AS INTEGER)) AS dep_hour
            FROM trips t
            JOIN stop_times st ON t.feed_id = st.feed_id AND t.trip_id = st.trip_id
            WHERE t.feed_id = :fid
            GROUP BY t.route_id, t.trip_id
        ),
        route_temporal_agg AS (
            SELECT 
                route_id,
                COUNT(*) AS total_daily_trips,
                COUNT(CASE WHEN dep_hour NOT IN :peak_hrs THEN 1 END) AS off_peak_trips
            FROM route_temporal
            GROUP BY route_id
        ),
        route_calendar AS (
            SELECT 
                t.route_id,
                BOOL_OR(c.saturday) AS has_sat,
                BOOL_OR(c.sunday) AS has_sun
            FROM trips t
            JOIN calendar c ON t.feed_id = c.feed_id AND t.service_id = c.service_id
            WHERE t.feed_id = :fid
            GROUP BY t.route_id
        )
        SELECT 
            rb.route_id,
            rb.route_short_name,
            rb.route_long_name,
            COALESCE(rt.transfer_routes_connected, 0) AS transfer_routes_connected,
            rb.stop_count,
            COALESCE(rta.total_daily_trips, 0) AS total_daily_trips,
            COALESCE(rta.off_peak_trips, 0) AS off_peak_trips,
            CASE 
                WHEN NOT COALESCE(rc.has_sat, FALSE) AND NOT COALESCE(rc.has_sun, FALSE) THEN 1.0
                ELSE 0.0
            END AS weekend_gap_flag
        FROM route_base rb
        LEFT JOIN route_transfers rt ON rb.route_id = rt.route_id
        LEFT JOIN route_temporal_agg rta ON rb.route_id = rta.route_id
        LEFT JOIN route_calendar rc ON rb.route_id = rc.route_id;
    """

    peak_tuple = tuple(all_peak_hours) if all_peak_hours else (-1,)
    df = pd.read_sql(
        text(query),
        engine,
        params={"fid": feed_id, "peak_hrs": peak_tuple}
    )

    if df.empty:
        return df

    # Calculate off_peak_headway in minutes: (off_peak_hours * 60) / off_peak_trips
    def calc_headway(trips: int) -> float:
        if trips > 0:
            return round((off_peak_hours_count * 60.0) / trips, 1)
        return float(off_peak_hours_count * 60.0)

    df["off_peak_headway"] = df["off_peak_trips"].apply(calc_headway)
    return df


def compute_composite_score(df: pd.DataFrame, weights: Dict[str, float]) -> pd.DataFrame:
    """
    Normalizes features and computes the Route Supply Gap Priority Index (RSGPI).
    Scales score from 0 to 100.
    """
    df_calc = df.copy()

    df_calc["norm_connectivity"] = min_max_normalize(df_calc["transfer_routes_connected"])
    df_calc["norm_off_peak_gap"] = min_max_normalize(df_calc["off_peak_headway"])
    df_calc["norm_weekend_deficit"] = df_calc["weekend_gap_flag"]
    df_calc["norm_stop_density"] = min_max_normalize(df_calc["stop_count"])

    w_conn = weights.get("network_connectivity", 0.35)
    w_headway = weights.get("off_peak_gap", 0.35)
    w_weekend = weights.get("weekend_deficit", 0.15)
    w_stops = weights.get("stop_density", 0.15)

    raw_score = (
        (w_conn * df_calc["norm_connectivity"]) +
        (w_headway * df_calc["norm_off_peak_gap"]) +
        (w_weekend * df_calc["norm_weekend_deficit"]) +
        (w_stops * df_calc["norm_stop_density"])
    )

    df_calc["composite_score"] = (raw_score * 100.0).round(2)
    df_calc["rank"] = df_calc["composite_score"].rank(ascending=False, method="min").astype(int)

    def assign_tier(rank_val: int, total_n: int) -> str:
        ratio = rank_val / total_n if total_n > 0 else 1.0
        if ratio <= 0.20:
            return "Tier 1 Priority Review"
        elif ratio <= 0.60:
            return "Tier 2 Moderate Review"
        return "Tier 3 Stable Corridor"

    total_routes = len(df_calc)
    df_calc["review_tier"] = df_calc["rank"].apply(lambda r: assign_tier(r, total_routes))

    return df_calc.sort_values(by=["rank", "composite_score"], ascending=[True, False])


def run_sensitivity_analysis(
    df: pd.DataFrame,
    baseline_weights: Dict[str, float],
    iterations: int = 500,
    perturbation: float = 0.20
) -> Dict[str, Any]:
    """
    Executes a Monte Carlo sensitivity analysis on the multi-criteria weights.
    Perturbs baseline weights uniformly by +/- perturbation% and re-normalizes.
    Evaluates ranking robustness using Spearman correlation and Top-10 overlap.
    """
    baseline_scored = compute_composite_score(df, baseline_weights)
    baseline_ranks = baseline_scored.set_index("route_id")["composite_score"]
    top_10_baseline = set(baseline_scored.nsmallest(min(10, len(baseline_scored)), "rank")["route_id"])
    bottom_10_baseline = set(baseline_scored.nlargest(min(10, len(baseline_scored)), "rank")["route_id"])

    spearman_scores: List[float] = []
    top_10_overlaps: List[float] = []
    bottom_10_overlaps: List[float] = []

    weight_keys = list(baseline_weights.keys())
    base_vals = np.array([baseline_weights[k] for k in weight_keys])

    np.random.seed(42)  # For reproducible audit stability

    for _ in range(iterations):
        deltas = np.random.uniform(-perturbation, perturbation, size=len(base_vals))
        perturbed = np.maximum(0.01, base_vals * (1.0 + deltas))
        sim_weights = perturbed / perturbed.sum()
        sim_dict = dict(zip(weight_keys, sim_weights))

        sim_scored = compute_composite_score(df, sim_dict)
        sim_scores = sim_scored.set_index("route_id")["composite_score"]

        rho = compute_spearman_rho(baseline_ranks, sim_scores)
        spearman_scores.append(rho)

        top_10_sim = set(sim_scored.nsmallest(min(10, len(sim_scored)), "rank")["route_id"])
        bottom_10_sim = set(sim_scored.nlargest(min(10, len(sim_scored)), "rank")["route_id"])

        denom = float(min(10, len(baseline_scored)))
        top_10_overlaps.append(len(top_10_baseline.intersection(top_10_sim)) / denom)
        bottom_10_overlaps.append(len(bottom_10_baseline.intersection(bottom_10_sim)) / denom)

    # Equal weights comparison
    equal_weights = {k: 1.0 / len(weight_keys) for k in weight_keys}
    equal_scored = compute_composite_score(df, equal_weights)
    equal_rho = compute_spearman_rho(baseline_ranks, equal_scored.set_index("route_id")["composite_score"])

    results = {
        "iterations": iterations,
        "perturbation_range": f"+/- {int(perturbation * 100)}%",
        "mean_spearman_rho": round(float(np.mean(spearman_scores)), 3),
        "std_spearman_rho": round(float(np.std(spearman_scores)), 3),
        "p5_spearman_rho": round(float(np.percentile(spearman_scores, 5)), 3),
        "mean_top10_overlap": round(float(np.mean(top_10_overlaps)) * 100, 1),
        "mean_bottom10_overlap": round(float(np.mean(bottom_10_overlaps)) * 100, 1),
        "equal_weights_rho": round(equal_rho, 3)
    }

    return results


def run_scoring_pipeline(
    engine: Optional[Engine] = None,
    feed_id: str = "chennai_mtc",
    feed_config: Optional[Dict[str, Any]] = None
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Executes the complete multi-feed route prioritization and sensitivity engine."""
    if engine is None:
        engine = config.get_db_engine()

    cfg = feed_config or {}
    baseline_weights = cfg.get("scoring_weights", {
        "network_connectivity": 0.35,
        "off_peak_gap": 0.35,
        "weekend_deficit": 0.15,
        "stop_density": 0.15
    })

    sim_cfg = cfg.get("sensitivity_analysis", {"iterations": 500, "perturbation_range": 0.20})
    iterations = int(sim_cfg.get("iterations", 500))
    perturbation = float(sim_cfg.get("perturbation_range", 0.20))

    logger.info("Extracting route features for feed '%s'...", feed_id)
    features_df = fetch_route_features(engine, feed_id, cfg)

    if features_df.empty:
        logger.warning("No routes found for feed '%s'. Ingest GTFS feed first.", feed_id)
        return pd.DataFrame(), {}

    logger.info("Computing composite priority scores for %d corridors...", len(features_df))
    scored_df = compute_composite_score(features_df, baseline_weights)

    logger.info("Running %d-iteration Monte Carlo sensitivity analysis...", iterations)
    sensitivity_results = run_sensitivity_analysis(features_df, baseline_weights, iterations, perturbation)
    sensitivity_results["feed_id"] = feed_id

    # Persist scores and sensitivity to PostgreSQL scoped by feed_id
    logger.info("Persisting route scores and sensitivity audit for feed '%s' to PostgreSQL...", feed_id)
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM scoring_sensitivity WHERE feed_id = :fid;"),
            {"fid": feed_id}
        )
        conn.execute(
            text("DELETE FROM route_scores WHERE feed_id = :fid;"),
            {"fid": feed_id}
        )

        for _, r in scored_df.iterrows():
            conn.execute(text("""
                INSERT INTO route_scores (
                    feed_id, route_id, route_short_name, route_long_name,
                    transfer_routes_connected, off_peak_headway, weekend_gap_flag, stop_count,
                    norm_connectivity, norm_off_peak_gap, norm_weekend_deficit, norm_stop_density,
                    composite_score, rank, review_tier
                ) VALUES (
                    :feed_id, :route_id, :route_short_name, :route_long_name,
                    :transfer_routes_connected, :off_peak_headway, :weekend_gap_flag, :stop_count,
                    :norm_connectivity, :norm_off_peak_gap, :norm_weekend_deficit, :norm_stop_density,
                    :composite_score, :rank, :review_tier
                );
            """), {
                "feed_id": feed_id,
                "route_id": r["route_id"],
                "route_short_name": r["route_short_name"],
                "route_long_name": r["route_long_name"],
                "transfer_routes_connected": int(r["transfer_routes_connected"]),
                "off_peak_headway": float(r["off_peak_headway"]),
                "weekend_gap_flag": float(r["weekend_gap_flag"]),
                "stop_count": int(r["stop_count"]),
                "norm_connectivity": float(r["norm_connectivity"]),
                "norm_off_peak_gap": float(r["norm_off_peak_gap"]),
                "norm_weekend_deficit": float(r["norm_weekend_deficit"]),
                "norm_stop_density": float(r["norm_stop_density"]),
                "composite_score": float(r["composite_score"]),
                "rank": int(r["rank"]),
                "review_tier": r["review_tier"]
            })

        conn.execute(text("""
            INSERT INTO scoring_sensitivity (
                feed_id, iterations, mean_spearman_rho, p5_spearman_rho,
                mean_top10_overlap, mean_bottom10_overlap, equal_weights_rho, evaluated_at
            ) VALUES (
                :feed_id, :iterations, :mean_spearman_rho, :p5_spearman_rho,
                :mean_top10_overlap, :mean_bottom10_overlap, :equal_weights_rho, NOW()
            );
        """), {
            "feed_id": feed_id,
            "iterations": sensitivity_results["iterations"],
            "mean_spearman_rho": sensitivity_results["mean_spearman_rho"],
            "p5_spearman_rho": sensitivity_results["p5_spearman_rho"],
            "mean_top10_overlap": sensitivity_results["mean_top10_overlap"],
            "mean_bottom10_overlap": sensitivity_results["mean_bottom10_overlap"],
            "equal_weights_rho": sensitivity_results["equal_weights_rho"]
        })

    # Save sensitivity results to JSON
    out_json = PROJECT_ROOT / "data" / f"sensitivity_{feed_id}.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(sensitivity_results, f, indent=2)

    if feed_id == "chennai_mtc":
        default_json = PROJECT_ROOT / "data" / "sensitivity_audit.json"
        with open(default_json, "w", encoding="utf-8") as f:
            json.dump(sensitivity_results, f, indent=2)

    return scored_df, sensitivity_results


if __name__ == "__main__":
    config.setup_logging()
    engine = config.get_db_engine()
    df_s, sens = run_scoring_pipeline(engine, "chennai_mtc")
    print(f"Computed scores for {len(df_s)} routes.")
    print("Sensitivity Results:", sens)
