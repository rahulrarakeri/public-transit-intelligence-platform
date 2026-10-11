# ====================================================================
# Public Transit Intelligence Platform - Automation Makefile
# Target Environment: macOS / Linux (Python 3.11+, PostgreSQL 14+)
# ====================================================================

PYTHON := ./venv/bin/python
PYTEST := ./venv/bin/pytest
STREAMLIT := ./venv/bin/streamlit

.PHONY: help install db-reset ingest-chennai ingest-sample ingest-all test app clean

help:
	@echo "Public Transit Intelligence Platform - Available Commands:"
	@echo "  make install         Install Python dependencies from requirements.txt"
	@echo "  make db-reset        Re-apply PostgreSQL multi-feed schema (sql/schema.sql)"
	@echo "  make ingest-chennai  Ingest Chennai MTC GTFS feed (primary case study)"
	@echo "  make ingest-sample   Ingest Sample City GTFS test fixture"
	@echo "  make ingest-all      Ingest both feeds for full multi-city benchmarking"
	@echo "  make test            Run pytest suite (unit, integration, multi-feed)"
	@echo "  make app             Launch executive Streamlit BI dashboard"
	@echo "  make clean           Remove __pycache__ and temporary artifacts"

install:
	$(PYTHON) -m pip install -r requirements.txt

db-reset:
	$(PYTHON) -c "import config, pathlib; from sqlalchemy import text; engine=config.get_db_engine(); sql=pathlib.Path('sql/schema.sql').read_text(); conn=engine.connect(); conn.execute(text(sql)); conn.commit(); print('PostgreSQL multi-feed schema reset complete.')"

ingest-chennai:
	$(PYTHON) -m src.ingest --feed chennai_mtc

ingest-sample:
	$(PYTHON) -m src.ingest --feed sample_city

ingest-all: ingest-chennai ingest-sample
	@echo "All transit feeds ingested successfully."

test:
	$(PYTEST) -v tests/

app:
	$(STREAMLIT) run app/app.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
