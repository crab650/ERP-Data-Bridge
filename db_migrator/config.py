from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class MigrationOptions:
    tables: list[str]
    batch_size: int = 5000
    if_exists: str = "recreate"
    include_data: bool = True
    include_primary_keys: bool = True
    include_indexes: bool = True
    preserve_identity: bool = True
    verify_row_counts: bool = True


@dataclass(frozen=True)
class MigrationConfig:
    source: dict[str, Any]
    target: dict[str, Any]
    options: MigrationOptions


def load_config(path: str | Path) -> MigrationConfig:
    with Path(path).open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)

    if not isinstance(raw, dict):
        raise ValueError("Config file must contain a YAML object.")

    source = _resolve_password(raw["source"], "source")
    target = _resolve_password(raw["target"], "target")
    options = raw.get("options", {})
    return MigrationConfig(
        source=source,
        target=target,
        options=MigrationOptions(
            tables=list(options.get("tables") or []),
            batch_size=int(options.get("batch_size", 5000)),
            if_exists=options.get("if_exists", "recreate"),
            include_data=bool(options.get("include_data", True)),
            include_primary_keys=bool(options.get("include_primary_keys", True)),
            include_indexes=bool(options.get("include_indexes", True)),
            preserve_identity=bool(options.get("preserve_identity", True)),
            verify_row_counts=bool(options.get("verify_row_counts", True)),
        ),
    )


def _resolve_password(config: dict[str, Any], section_name: str) -> dict[str, Any]:
    resolved = dict(config)
    password_env = resolved.get("password_env")
    if password_env:
        password = os.getenv(str(password_env))
        if password is None:
            raise ValueError(
                f"{section_name}.password_env is set to {password_env}, "
                "but that environment variable is not defined."
            )
        resolved["password"] = password
    return resolved
