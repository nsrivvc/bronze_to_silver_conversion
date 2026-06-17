"""
base.py
=======
The shared pattern every Silver transformation follows.

To add a new Silver table, create a file in src/transformations/ that subclasses
SilverTransformation and implements three things:

    name            -> the silver table name (also the registry key / CLI name)
    bronze_sources  -> Bronze tables it reads (used for a pre-run existence check)
    create_table_sql()  -> CREATE TABLE IF NOT EXISTS ...   (idempotent DDL)
    transform_sql()     -> INSERT ... SELECT ... ON CONFLICT DO UPDATE  (idempotent load)

...then decorate the class with @register. That's it — the runner discovers it.

The methods return plain SQL strings, so this module deliberately does NOT import
SQLAlchemy. The runner passes a live Connection to run().
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ..config import settings


class SilverTransformation(ABC):
    # --- override these in each subclass -------------------------------------
    name: str = ""                 # e.g. "silver_firm_transport_rate"
    bronze_sources: List[str] = []  # e.g. ["gtran_firm", "gtran_rates", "gtran_loc"]

    # --- schema names come from config so they're not hardcoded --------------
    def __init__(self) -> None:
        self.bronze_schema = settings.bronze_schema
        self.silver_schema = settings.silver_schema
        if not self.name:
            raise ValueError(f"{type(self).__name__} must set a `name`.")

    # --- implement these in each subclass ------------------------------------
    @abstractmethod
    def create_table_sql(self) -> str:
        """Idempotent DDL: CREATE SCHEMA / CREATE TABLE IF NOT EXISTS ... ."""

    @abstractmethod
    def transform_sql(self) -> str:
        """Idempotent load: INSERT ... SELECT ... ON CONFLICT (...) DO UPDATE ... ."""

    # --- default execution; override only for non-SQL (pure-Python) loads ----
    def run(self, conn) -> int:
        """Create the table if needed, then upsert. Returns rows affected.

        `conn` is a SQLAlchemy Connection supplied by the runner inside a
        transaction, so partial failures roll back automatically.
        """
        conn.exec_driver_sql(self.create_table_sql())
        result = conn.exec_driver_sql(self.transform_sql())
        return result.rowcount if result.rowcount is not None else -1
