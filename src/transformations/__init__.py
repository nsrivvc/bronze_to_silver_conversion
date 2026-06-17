"""
transformations package
========================
Auto-discovers every transformation module in this folder so that simply
*creating a file here* (with a @register-ed class) makes it available to the
runner. No central list to maintain.

To add a new Silver table: copy silver_firm_transport_rate.py to a new file,
rename the class, set `name` / `bronze_sources`, and rewrite the two SQL methods.
"""

from __future__ import annotations

import importlib
import pkgutil

# Import every sibling module so its @register decorator runs on import.
for _module in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module.name}")
