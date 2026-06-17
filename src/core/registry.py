"""
registry.py
===========
A tiny registry so transformations self-register. Each transformation file does:

    from ..core.registry import register
    from ..core.base import SilverTransformation

    @register
    class MySilverTable(SilverTransformation):
        name = "silver_my_table"
        ...

The runner reads REGISTRY (a name -> instance map) after importing the
transformations package.
"""

from __future__ import annotations

from typing import Dict, Type

from .base import SilverTransformation

REGISTRY: Dict[str, SilverTransformation] = {}


def register(cls: Type[SilverTransformation]) -> Type[SilverTransformation]:
    """Class decorator: instantiate and add to the registry, keyed by `name`."""
    instance = cls()
    if instance.name in REGISTRY:
        raise ValueError(f"Duplicate transformation name: {instance.name!r}")
    REGISTRY[instance.name] = instance
    return cls
