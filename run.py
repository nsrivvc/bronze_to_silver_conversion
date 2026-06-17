#!/usr/bin/env python3
"""
run.py
======
Batch entrypoint for the Bronze -> Silver transformations.

Examples:
    python run.py --list                              # show registered transformations
    python run.py --show-sql silver_firm_transport_rate   # print SQL (no DB needed)
    python run.py --table silver_firm_transport_rate  # run one
    python run.py --all                               # run everything

Exit code is non-zero if any transformation failed (so schedulers flag the job).
"""

from __future__ import annotations

import argparse
import sys

from src.logging_config import get_logger

log = get_logger("run")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bronze -> Silver batch runner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List registered transformations")
    group.add_argument("--inspect", action="store_true",
                       help="Read-only snapshot: existing Bronze/Silver tables + row counts (no transforms run)")
    group.add_argument("--table", metavar="NAME", help="Run a single transformation by name")
    group.add_argument("--all", action="store_true", help="Run all transformations")
    group.add_argument("--show-sql", metavar="NAME", help="Print a transformation's SQL and exit")
    args = parser.parse_args(argv)

    # Import here so --help works without importing the DB stack.
    from src.core import runner
    from src.core.registry import REGISTRY

    if args.list:
        print("Registered transformations:")
        for name in runner.list_transformations():
            print(f"  - {name}  (reads: {', '.join(REGISTRY[name].bronze_sources)})")
        return 0

    if args.show_sql:
        t = REGISTRY.get(args.show_sql)
        if not t:
            log.error("Unknown transformation: %s", args.show_sql)
            return 2
        print("-- ===== CREATE TABLE =====")
        print(t.create_table_sql())
        print("\n-- ===== TRANSFORM =====")
        print(t.transform_sql())
        return 0

    if args.inspect:
        from src.core import inspect as inspect_mod
        inspect_mod.inspect()
        return 0

    if args.table:
        result = runner.run_one(args.table)
        return 1 if result.status == "failed" else 0

    if args.all:
        results = runner.run_all()
        return 1 if runner.any_failed(results) else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
