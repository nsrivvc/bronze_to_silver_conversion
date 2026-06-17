"""
config.py
=========
All configuration comes from environment variables (loaded from a local .env
if python-dotenv is installed). Nothing is hardcoded.

WHERE TO CHANGE THINGS:
  * Point at a different database  -> DATABASE_URL (or the PG* parts) in .env
  * Rename the raw/curated schemas -> BRONZE_SCHEMA / SILVER_SCHEMA in .env
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

try:  # optional convenience for local runs
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


def _build_url() -> str:
    """Return a SQLAlchemy URL, either from DATABASE_URL or from PG* parts."""
    url = os.getenv("DATABASE_URL")
    if url:
        # SQLAlchemy wants the "postgresql://" scheme (not "postgres://").
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    # Fallback: assemble from individual parts (handy for a local/dummy DB).
    user = os.getenv("PGUSER", "postgres")
    pwd = os.getenv("PGPASSWORD", "postgres")
    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    db = os.getenv("PGDATABASE", "pipeline")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


@dataclass
class Settings:
    database_url: str = field(default_factory=_build_url)
    bronze_schema: str = field(default_factory=lambda: os.getenv("BRONZE_SCHEMA", "bronze"))
    silver_schema: str = field(default_factory=lambda: os.getenv("SILVER_SCHEMA", "silver"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


# Single shared instance imported across the codebase.
settings = Settings()
