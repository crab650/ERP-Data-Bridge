from __future__ import annotations

from typing import Any

from .adapters.base import DatabaseSource, DatabaseTarget
from .adapters.mssql import MssqlSource, MssqlTarget
from .adapters.sqlite import SqliteTarget


def create_source(config: dict[str, Any]) -> DatabaseSource:
    source_type = config.get("type")
    if source_type == "mssql":
        return MssqlSource(config)
    raise ValueError(f"Unsupported source type: {source_type}")


def create_target(config: dict[str, Any]) -> DatabaseTarget:
    target_type = config.get("type")
    if target_type == "mssql":
        return MssqlTarget(config)
    if target_type == "sqlite":
        return SqliteTarget(config)
    raise ValueError(f"Unsupported target type: {target_type}")
