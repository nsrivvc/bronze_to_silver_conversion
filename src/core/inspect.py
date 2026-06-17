"""
inspect.py
==========
Read-only diagnostics. Answers "what's actually in the database right now?"
WITHOUT running any transformation:

  * every table that exists in the Bronze schema, with row counts
  * every table that exists in the Silver schema, with row counts
  * per registered transformation: are its Bronze sources present, and how many
    rows do they hold, and does its target Silver table exist yet

Use this before a run to confirm the inputs, and after a run to confirm outputs.
Nothing here writes or alters data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from ..config import settings
from ..db.connection import get_engine
from ..logging_config import get_logger
from .registry import REGISTRY

# Ensure transformations are discovered even if inspect is invoked directly,
# so the readiness section is always populated.
from .. import transformations  # noqa: F401  (side-effect import)

log = get_logger(__name__)


@dataclass
class TableInfo:
    schema: str
    name: str
    row_count: int


def _quote(identifier: str) -> str:
    """Safely double-quote a Postgres identifier (names come from the catalog)."""
    return '"' + identifier.replace('"', '""') + '"'


def schema_exists(conn, schema: str) -> bool:
    from sqlalchemy import text

    row = conn.execute(
        text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"),
        {"s": schema},
    ).first()
    return row is not None


def list_schema_tables(conn, schema: str) -> List[str]:
    from sqlalchemy import text

    rows = conn.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = :s AND table_type = 'BASE TABLE' "
            "ORDER BY table_name"
        ),
        {"s": schema},
    ).all()
    return [r[0] for r in rows]


def count_rows(conn, schema: str, table: str) -> int:
    from sqlalchemy import text

    sql = f"SELECT count(*) FROM {_quote(schema)}.{_quote(table)}"
    return conn.execute(text(sql)).scalar_one()


def snapshot_schema(conn, schema: str) -> List[TableInfo]:
    return [
        TableInfo(schema, t, count_rows(conn, schema, t))
        for t in list_schema_tables(conn, schema)
    ]


def inspect() -> None:
    """Print a full Bronze/Silver snapshot plus per-transformation readiness."""
    engine = get_engine()
    bronze_schema = settings.bronze_schema
    silver_schema = settings.silver_schema

    with engine.connect() as conn:  # read-only; no transaction/commit needed
        bronze_exists = schema_exists(conn, bronze_schema)
        bronze = snapshot_schema(conn, bronze_schema) if bronze_exists else []
        silver = snapshot_schema(conn, silver_schema)
        bronze_counts: Dict[str, int] = {t.name: t.row_count for t in bronze}
        silver_names = {t.name for t in silver}

        if bronze_exists:
            _print_table_block(f"BRONZE schema '{bronze_schema}'", bronze)
        else:
            print(f"\nBRONZE schema '{bronze_schema}'")
            print("-" * 72)
            print("  No bronze schema detected in database (neon).")
        _print_table_block(f"SILVER schema '{silver_schema}'", silver)

        print("\nTransformation readiness")
        print("-" * 72)
        if not REGISTRY:
            print("  (no transformations registered)")
        for name in sorted(REGISTRY):
            t = REGISTRY[name]
            missing = [s for s in t.bronze_sources if s not in bronze_counts]
            target = t.name.replace("silver_", "", 1)  # display hint only
            ready = "READY " if not missing else "BLOCKED"
            print(f"\n  [{ready}] {name}")
            for src in t.bronze_sources:
                if src in bronze_counts:
                    print(f"      reads {bronze_schema}.{src:<16} {bronze_counts[src]:>8} rows")
                else:
                    print(f"      reads {bronze_schema}.{src:<16}   MISSING")
            # does a matching silver table already exist?
            existing = [s for s in silver_names if target in s or s in name]
            note = f"target silver table exists ({existing[0]})" if existing else "target silver table not created yet"
            print(f"      -> {note}")
    print()


def _print_table_block(title: str, tables: List[TableInfo]) -> None:
    print(f"\n{title}")
    print("-" * 72)
    if not tables:
        print("  (no tables found)")
        return
    width = max(len(t.name) for t in tables)
    for t in tables:
        print(f"  {t.name:<{width}}  {t.row_count:>10} rows")
    print(f"  {'TOTAL':<{width}}  {sum(t.row_count for t in tables):>10} rows "
          f"across {len(tables)} table(s)")
