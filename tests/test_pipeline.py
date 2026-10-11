"""
Transit Intelligence Platform - Unit, Integration & Multi-Feed Pipeline Tests

Validates:
- Config loading and schema compliance across feeds
- Headway calculations & service classifications
- Score Min-Max normalization & Spearman rank correlation
- Multi-feed database isolation (Chennai MTC & Sample City fixture)
- Automated data quality checks per feed
- End-to-end ingestion execution on fixture feed
"""

import sys
from pathlib import Path
import pytest
import pandas as pd
import numpy as np
import yaml

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from src.ingest import load_feed_config, ingest_feed
from src.scoring import min_max_normalize, compute_spearman_rho, compute_composite_score
from src.data_quality import run_data_quality_checks
from src.insights import compute_headline_findings


def test_config_loading_and_validation():
    """Validates that YAML configs for chennai_mtc, sample_city, and template are well-formed."""
    cfg_chennai = load_feed_config("chennai_mtc")
    assert cfg_chennai["feed_id"] == "chennai_mtc"
    assert "bounding_box" in cfg_chennai
    assert "peak_hours" in cfg_chennai
    assert "scoring_weights" in cfg_chennai
    assert sum(cfg_chennai["scoring_weights"].values()) == pytest.approx(1.0)

    cfg_sample = load_feed_config("sample_city")
    assert cfg_sample["feed_id"] == "sample_city"
    assert "bounding_box" in cfg_sample
    assert "peak_hours" in cfg_sample
    assert "scoring_weights" in cfg_sample

    template_path = PROJECT_ROOT / "configs" / "_template.yaml"
    assert template_path.is_file()
    with open(template_path, "r", encoding="utf-8") as f:
        cfg_template = yaml.safe_load(f)
    assert "feed_id" in cfg_template
    assert "scoring_weights" in cfg_template


def test_min_max_normalization():
    """Validates that min-max normalization bounds values between 0.0 and 1.0."""
    s = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
    norm = min_max_normalize(s)
    assert norm.min() == 0.0
    assert norm.max() == 1.0
    assert norm.iloc[2] == 0.5


def test_min_max_normalization_identical_values():
    """Validates edge case where all values are identical."""
    s = pd.Series([15.0, 15.0, 15.0])
    norm = min_max_normalize(s)
    assert (norm == 0.5).all()


def test_spearman_rank_correlation():
    """Validates rank correlation computation without external scipy dependency."""
    s1 = pd.Series([1, 2, 3, 4, 5])
    s2 = pd.Series([10, 20, 30, 40, 50])
    assert pytest.approx(compute_spearman_rho(s1, s2), 0.001) == 1.0

    s3 = pd.Series([50, 40, 30, 20, 10])
    assert pytest.approx(compute_spearman_rho(s1, s3), 0.001) == -1.0


def test_headway_calculation_logic():
    """Tests operational headway conversion formula: 1440 / daily_trips."""
    def calc_headway(trips: int) -> float:
        return round(1440.0 / trips, 1) if trips > 0 else 1440.0

    assert calc_headway(10) == 144.0
    assert calc_headway(24) == 60.0
    assert calc_headway(48) == 30.0
    assert calc_headway(96) == 15.0


def test_composite_scoring_weights():
    """Tests that composite score computation properly respects weights and scales to 0-100."""
    df_dummy = pd.DataFrame({
        "route_id": ["R1", "R2"],
        "transfer_routes_connected": [10, 20],
        "off_peak_headway": [180.0, 540.0],
        "weekend_gap_flag": [0.0, 1.0],
        "stop_count": [15, 25]
    })
    weights = {
        "network_connectivity": 0.35,
        "off_peak_gap": 0.35,
        "weekend_deficit": 0.15,
        "stop_density": 0.15
    }
    scored = compute_composite_score(df_dummy, weights)
    assert "composite_score" in scored.columns
    assert "rank" in scored.columns
    assert "review_tier" in scored.columns
    assert scored.loc[scored["route_id"] == "R2", "composite_score"].iloc[0] == 100.0
    assert scored.loc[scored["route_id"] == "R1", "composite_score"].iloc[0] == 0.0


def test_multi_feed_database_isolation():
    """Validates that both feeds coexist in PostgreSQL without ID collisions or data leakage."""
    engine = config.get_db_engine()
    from sqlalchemy import text
    with engine.connect() as conn:
        feeds = set(r[0] for r in conn.execute(text("SELECT feed_id FROM feeds;")).fetchall())
        assert "chennai_mtc" in feeds
        assert "sample_city" in feeds

        # Chennai record counts
        c_routes = conn.execute(text("SELECT COUNT(*) FROM routes WHERE feed_id = 'chennai_mtc';")).scalar()
        c_stops = conn.execute(text("SELECT COUNT(*) FROM stops WHERE feed_id = 'chennai_mtc';")).scalar()
        c_trips = conn.execute(text("SELECT COUNT(*) FROM trips WHERE feed_id = 'chennai_mtc';")).scalar()

        # Sample city record counts
        s_routes = conn.execute(text("SELECT COUNT(*) FROM routes WHERE feed_id = 'sample_city';")).scalar()
        s_stops = conn.execute(text("SELECT COUNT(*) FROM stops WHERE feed_id = 'sample_city';")).scalar()
        s_trips = conn.execute(text("SELECT COUNT(*) FROM trips WHERE feed_id = 'sample_city';")).scalar()

    assert c_routes == 50
    assert c_stops == 150
    assert c_trips == 500

    assert s_routes == 10
    assert s_stops == 30
    assert s_trips == 100


def test_data_quality_checks_per_feed():
    """Validates that automated data quality audit passes for both feeds."""
    engine = config.get_db_engine()

    # Chennai MTC audit
    report_chennai = run_data_quality_checks(engine, "chennai_mtc", load_feed_config("chennai_mtc"))
    res_c = {r["check_name"]: r["status"] for r in report_chennai["results"]}
    assert res_c["Null Critical Fields"] == "PASS"
    assert res_c["Duplicate Primary Keys"] == "PASS"
    assert res_c["Referential Integrity"] == "PASS"
    assert res_c["Geospatial Bounding Box"] == "PASS"

    # Sample City audit
    report_sample = run_data_quality_checks(engine, "sample_city", load_feed_config("sample_city"))
    res_s = {r["check_name"]: r["status"] for r in report_sample["results"]}
    assert res_s["Null Critical Fields"] == "PASS"
    assert res_s["Duplicate Primary Keys"] == "PASS"
    assert res_s["Referential Integrity"] == "PASS"
    assert res_s["Geospatial Bounding Box"] == "PASS"


def test_end_to_end_fixture_ingestion():
    """Validates end-to-end ingestion execution on the sample_city GTFS fixture."""
    counts = ingest_feed("sample_city")
    assert counts["routes"] == 10
    assert counts["stops"] == 30
    assert counts["trips"] == 100
    assert counts["stop_times"] == 600
