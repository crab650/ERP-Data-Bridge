from __future__ import annotations

import logging
import time

from tqdm import tqdm

from .adapters.base import DatabaseSource, DatabaseTarget, TableRef
from .console import BLUE, color
from .config import MigrationOptions


logger = logging.getLogger(__name__)


class Migrator:
    def __init__(
        self,
        source: DatabaseSource,
        target: DatabaseTarget,
        options: MigrationOptions,
        dry_run: bool = False,
    ) -> None:
        self.source = source
        self.target = target
        self.options = options
        self.dry_run = dry_run

    def run(self) -> None:
        tables = self._select_tables()
        logger.info("Found %s table(s) to migrate.", len(tables))

        for index, table in enumerate(tables, start=1):
            started_at = time.monotonic()
            logger.info(
                "[%s/%s] Preparing %s",
                index,
                len(tables),
                color(table.full_name, BLUE),
            )
            schema = self.source.get_table_schema(table)
            if not self.options.include_primary_keys:
                schema.primary_key = []
                schema.primary_key_type_desc = None
            if not self.options.include_indexes:
                schema.indexes = []

            if self.dry_run:
                self._preview_table(schema)
                continue

            should_copy = self.target.prepare_table(schema, self.options.if_exists)

            if not should_copy:
                logger.info("Skipping existing target table %s", table.full_name)
                continue

            if self.options.include_data:
                self._copy_data(schema)
                if self.options.verify_row_counts:
                    self._verify_row_count(schema.table)

            if self.options.include_indexes and schema.indexes:
                logger.info("Creating %s index(es) on %s", len(schema.indexes), table.full_name)
                self.target.create_indexes(schema)

            elapsed = time.monotonic() - started_at
            logger.info("Finished %s in %.1fs", table.full_name, elapsed)

    def _select_tables(self) -> list[TableRef]:
        available = self.source.list_tables()
        requested = set(self.options.tables)
        if not requested:
            return available

        selected = []
        available_by_full_name = {table.full_name: table for table in available}
        available_by_name = {table.name: table for table in available}
        for table_name in self.options.tables:
            table = available_by_full_name.get(table_name) or available_by_name.get(table_name)
            if table is None:
                raise ValueError(f"Requested table not found in source database: {table_name}")
            selected.append(table)
        return selected

    def _copy_data(self, schema) -> None:
        where_clause = self.options.where.get(schema.table.full_name) or self.options.where.get(schema.table.name)
        total = self.source.count_rows(schema.table, where_clause)
        logger.info("Copying %s row(s) from %s", total, schema.table.full_name)

        with tqdm(
            total=total,
            desc=schema.table.full_name,
            unit="rows",
            leave=True,
            colour="cyan",
        ) as progress:
            for rows in self.source.iter_rows(schema, self.options.batch_size, where_clause):
                self.target.insert_rows(schema, rows, self.options.preserve_identity)
                progress.update(len(rows))

    def _verify_row_count(self, table: TableRef) -> None:
        where_clause = self.options.where.get(table.full_name) or self.options.where.get(table.name)
        source_count = self.source.count_rows(table, where_clause)
        target_count = self.target.count_rows(table)
        if source_count != target_count:
            raise ValueError(
                f"Row count mismatch for {table.full_name}: "
                f"source={source_count}, target={target_count}"
            )
        logger.info("Verified row count for %s: %s", table.full_name, source_count)

    def _preview_table(self, schema) -> None:
        where_clause = self.options.where.get(schema.table.full_name) or self.options.where.get(schema.table.name)
        total = self.source.count_rows(schema.table, where_clause) if self.options.include_data else 0
        logger.info(
            "DRY RUN %s: columns=%s, primary_key=%s, rows=%s, if_exists=%s",
            schema.table.full_name,
            len(schema.columns),
            ",".join(schema.primary_key) if schema.primary_key else "(none)",
            total,
            self.options.if_exists,
        )
        if schema.indexes:
            logger.info(
                "DRY RUN %s: indexes=%s",
                schema.table.full_name,
                ", ".join(index.name for index in schema.indexes),
            )
