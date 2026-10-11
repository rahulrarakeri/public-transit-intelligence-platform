"""
Public Transit Intelligence Platform
Configuration and Database Connection Utility

Manages environment variables, project paths, and PostgreSQL database connections.
"""

import os
import logging
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# Base project paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_GTFS_ZIP = DATA_DIR / "gtfs_feed.zip"
SQL_DIR = BASE_DIR / "sql"

# Load environment configuration from .env file
load_dotenv(dotenv_path=BASE_DIR / ".env")

# Database connection parameters with fallback defaults for local dev
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "transit_db")
DB_USER = os.getenv("DB_USER", "transit_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "transit123")

# Construct SQLAlchemy database URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# Normalize legacy postgres:// scheme to postgresql+psycopg2:// if needed
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)


def setup_logging(level: int = logging.INFO) -> None:
    """Configures a standardized console logging format."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def get_db_engine(pool_size: int = 5, max_overflow: int = 10) -> Engine:
    """
    Creates and returns a pooled SQLAlchemy engine for PostgreSQL.
    Uses pool_pre_ping to automatically reconnect on stale connections.
    """
    return create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow
    )
