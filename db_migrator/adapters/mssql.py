from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable, Sequence

import pyodbc

from .base import (
    Column,
    DatabaseSource,
    DatabaseTarget,
    Index,
    IndexColumn,
    TableRef,
    TableSchema,
)


def quote_ident(name: str) -> str:
    return "[" + name.replace("]", "]]") + "]"


def quote_table(table: TableRef) -> str:
    return f"{quote_ident(table.schema)}.{quote_ident(table.name)}"


def build_connection_string(config: dict[str, Any]) -> str:
    driver = config.get("driver", "ODBC Driver 17 for SQL Server")
    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={config['server']}",
        f"DATABASE={config['database']}",
    ]

    if config.get("trusted_connection"):
        parts.append("Trusted_Connection=yes")
    else:
        parts.extend([f"UID={config['username']}", f"PWD={config['password']}"])

    if config.get("trust_server_certificate", True):
        parts.append("TrustServerCertificate=yes")

    if "encrypt" in config:
        parts.append(f"Encrypt={'yes' if config['encrypt'] else 'no'}")

    return ";".join(parts)


def connect(config: dict[str, Any]) -> pyodbc.Connection:
    return pyodbc.connect(build_connection_string(config), autocommit=False)


class MssqlSource(DatabaseSource):
    def __init__(self, config: dict[str, Any]) -> None:
        self.connection = connect(config)

    def list_tables(self) -> list[TableRef]:
        sql = """
            SELECT s.name AS schema_name, t.name AS table_name
            FROM sys.tables t
            INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
            WHERE t.is_ms_shipped = 0
            ORDER BY s.name, t.name
        """
        cursor = self.connection.cursor()
        return [TableRef(row.schema_name, row.table_name) for row in cursor.execute(sql)]

    def get_table_schema(self, table: TableRef) -> TableSchema:
        column_sql = """
            SELECT
                c.name,
                ty.name AS data_type,
                c.max_length,
                c.precision,
                c.scale,
                c.is_nullable,
                c.is_identity,
                c.is_computed
            FROM sys.columns c
            INNER JOIN sys.types ty ON ty.user_type_id = c.user_type_id
            INNER JOIN sys.tables t ON t.object_id = c.object_id
            INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
            WHERE s.name = ? AND t.name = ?
            ORDER BY c.column_id
        """
        pk_sql = """
            SELECT c.name, i.type_desc
            FROM sys.key_constraints kc
            INNER JOIN sys.indexes i
                ON i.object_id = kc.parent_object_id
                AND i.index_id = kc.unique_index_id
            INNER JOIN sys.index_columns ic
                ON ic.object_id = kc.parent_object_id
                AND ic.index_id = kc.unique_index_id
            INNER JOIN sys.columns c
                ON c.object_id = ic.object_id
                AND c.column_id = ic.column_id
            INNER JOIN sys.tables t ON t.object_id = kc.parent_object_id
            INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
            WHERE kc.type = 'PK' AND s.name = ? AND t.name = ?
            ORDER BY ic.key_ordinal
        """
        cursor = self.connection.cursor()
        columns = [
            Column(
                name=row.name,
                data_type=row.data_type,
                max_length=row.max_length,
                precision=row.precision,
                scale=row.scale,
                nullable=bool(row.is_nullable),
                is_identity=bool(row.is_identity),
                is_computed=bool(row.is_computed),
            )
            for row in cursor.execute(column_sql, table.schema, table.name)
        ]
        pk_rows = list(cursor.execute(pk_sql, table.schema, table.name))
        primary_key = [row.name for row in pk_rows]
        primary_key_type_desc = pk_rows[0].type_desc if pk_rows else None
        return TableSchema(
            table=table,
            columns=columns,
            primary_key=primary_key,
            primary_key_type_desc=primary_key_type_desc,
            indexes=self._get_indexes(table),
        )

    def _get_indexes(self, table: TableRef) -> list[Index]:
        sql = """
            SELECT
                i.name AS index_name,
                i.is_unique,
                i.type_desc,
                i.filter_definition,
                c.name AS column_name,
                ic.is_descending_key,
                ic.is_included_column,
                ic.key_ordinal,
                ic.index_column_id
            FROM sys.indexes i
            INNER JOIN sys.tables t ON t.object_id = i.object_id
            INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
            INNER JOIN sys.index_columns ic
                ON ic.object_id = i.object_id
                AND ic.index_id = i.index_id
            INNER JOIN sys.columns c
                ON c.object_id = ic.object_id
                AND c.column_id = ic.column_id
            WHERE
                s.name = ?
                AND t.name = ?
                AND i.is_primary_key = 0
                AND i.is_hypothetical = 0
                AND i.is_disabled = 0
                AND i.type IN (1, 2)
            ORDER BY i.index_id, ic.key_ordinal, ic.index_column_id
        """
        cursor = self.connection.cursor()
        indexes: dict[str, Index] = {}
        for row in cursor.execute(sql, table.schema, table.name):
            index = indexes.get(row.index_name)
            if index is None:
                index = Index(
                    name=row.index_name,
                    unique=bool(row.is_unique),
                    type_desc=row.type_desc,
                    key_columns=[],
                    included_columns=[],
                    filter_definition=row.filter_definition,
                )
                indexes[row.index_name] = index

            if row.is_included_column:
                index.included_columns.append(row.column_name)
            else:
                index.key_columns.append(
                    IndexColumn(
                        name=row.column_name,
                        descending=bool(row.is_descending_key),
                    )
                )
        return list(indexes.values())

    def count_rows(self, table: TableRef, where_clause: str | None = None) -> int:
        cursor = self.connection.cursor()
        sql = f"SELECT COUNT_BIG(*) FROM {quote_table(table)}"
        if where_clause:
            sql += f" WHERE {where_clause}"
        row = cursor.execute(sql).fetchone()
        return int(row[0])

    def iter_rows(
        self,
        schema: TableSchema,
        batch_size: int,
        where_clause: str | None = None,
    ) -> Iterable[list[tuple[Any, ...]]]:
        columns = ", ".join(quote_ident(column.name) for column in schema.insertable_columns)
        sql = f"SELECT {columns} FROM {quote_table(schema.table)}"
        if where_clause:
            sql += f" WHERE {where_clause}"
        cursor = self.connection.cursor()
        cursor.execute(sql)
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            yield [tuple(row) for row in rows]

    def close(self) -> None:
        self.connection.close()


class MssqlTarget(DatabaseTarget):
    def __init__(self, config: dict[str, Any]) -> None:
        self.connection = connect(config)

    def prepare_table(self, schema: TableSchema, if_exists: str) -> bool:
        if if_exists not in {"skip", "truncate", "recreate"}:
            raise ValueError("if_exists must be one of: skip, truncate, recreate")

        cursor = self.connection.cursor()
        self._ensure_schema(schema.table.schema)
        exists = self._table_exists(schema.table)

        if exists and if_exists == "skip":
            return False
        if exists and if_exists == "truncate":
            cursor.execute(f"TRUNCATE TABLE {quote_table(schema.table)}")
            self.connection.commit()
            return True
        if exists and if_exists == "recreate":
            cursor.execute(f"DROP TABLE {quote_table(schema.table)}")
            self.connection.commit()

        create_sql = self._build_create_table_sql(schema)
        cursor.execute(create_sql)
        self.connection.commit()
        return True

    def insert_rows(
        self,
        schema: TableSchema,
        rows: Sequence[tuple[Any, ...]],
        preserve_identity: bool,
    ) -> None:
        if not rows:
            return

        columns = schema.insertable_columns
        column_names = ", ".join(quote_ident(column.name) for column in columns)
        placeholders = ", ".join("?" for _ in columns)
        sql = f"INSERT INTO {quote_table(schema.table)} ({column_names}) VALUES ({placeholders})"
        has_identity = any(column.is_identity for column in columns)

        cursor = self.connection.cursor()
        cursor.fast_executemany = True
        with self._identity_insert(schema.table, preserve_identity and has_identity):
            cursor.executemany(sql, rows)
            self.connection.commit()

    def create_indexes(self, schema: TableSchema) -> None:
        cursor = self.connection.cursor()
        for index in schema.indexes:
            if not index.key_columns:
                continue
            cursor.execute(self._build_create_index_sql(schema.table, index))
        self.connection.commit()

    def count_rows(self, table: TableRef) -> int:
        cursor = self.connection.cursor()
        row = cursor.execute(f"SELECT COUNT_BIG(*) FROM {quote_table(table)}").fetchone()
        return int(row[0])

    def close(self) -> None:
        self.connection.close()

    def _ensure_schema(self, schema_name: str) -> None:
        cursor = self.connection.cursor()
        sql = f"""
            IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = ?)
            BEGIN
                EXEC('CREATE SCHEMA {quote_ident(schema_name)}')
            END
        """
        cursor.execute(sql, schema_name)
        self.connection.commit()

    def _table_exists(self, table: TableRef) -> bool:
        cursor = self.connection.cursor()
        row = cursor.execute(
            """
            SELECT 1
            FROM sys.tables t
            INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
            WHERE s.name = ? AND t.name = ?
            """,
            table.schema,
            table.name,
        ).fetchone()
        return row is not None

    def _build_create_table_sql(self, schema: TableSchema) -> str:
        column_defs = [self._column_definition(column) for column in schema.columns]
        if schema.primary_key:
            pk_cols = ", ".join(quote_ident(column) for column in schema.primary_key)
            pk_name = quote_ident(f"PK_{schema.table.schema}_{schema.table.name}")
            pk_type = self._format_index_type(schema.primary_key_type_desc)
            column_defs.append(f"CONSTRAINT {pk_name} PRIMARY KEY {pk_type} ({pk_cols})")
        body = ",\n    ".join(column_defs)
        return f"CREATE TABLE {quote_table(schema.table)} (\n    {body}\n)"

    def _build_create_index_sql(self, table: TableRef, index: Index) -> str:
        unique = "UNIQUE " if index.unique else ""
        index_type = self._format_index_type(index.type_desc)
        key_columns = ", ".join(
            f"{quote_ident(column.name)} {'DESC' if column.descending else 'ASC'}"
            for column in index.key_columns
        )
        include = ""
        if index.included_columns:
            included = ", ".join(quote_ident(column) for column in index.included_columns)
            include = f" INCLUDE ({included})"
        filter_clause = f" WHERE {index.filter_definition}" if index.filter_definition else ""
        index_name = quote_ident(index.name)
        create_sql = (
            f"CREATE {unique}{index_type} INDEX {index_name} "
            f"ON {quote_table(table)} ({key_columns}){include}{filter_clause}"
        )
        escaped_name = index.name.replace("'", "''")
        return f"""
            IF NOT EXISTS (
                SELECT 1
                FROM sys.indexes i
                INNER JOIN sys.tables t ON t.object_id = i.object_id
                INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
                WHERE s.name = '{table.schema.replace("'", "''")}'
                    AND t.name = '{table.name.replace("'", "''")}'
                    AND i.name = '{escaped_name}'
            )
            BEGIN
                {create_sql}
            END
        """

    def _format_index_type(self, type_desc: str | None) -> str:
        if type_desc == "CLUSTERED":
            return "CLUSTERED"
        return "NONCLUSTERED"

    def _column_definition(self, column: Column) -> str:
        if column.is_computed:
            raise ValueError(
                f"Computed column {column.name} is not supported for CREATE TABLE yet."
            )

        parts = [quote_ident(column.name), self._format_type(column)]
        if column.is_identity:
            parts.append("IDENTITY(1,1)")
        parts.append("NULL" if column.nullable else "NOT NULL")
        return " ".join(parts)

    def _format_type(self, column: Column) -> str:
        data_type = column.data_type.lower()
        if data_type in {"varchar", "char", "varbinary", "binary"}:
            if column.max_length == -1:
                return f"{data_type}(max)"
            return f"{data_type}({column.max_length})"
        if data_type in {"nvarchar", "nchar"}:
            if column.max_length == -1:
                return f"{data_type}(max)"
            return f"{data_type}({int((column.max_length or 0) / 2)})"
        if data_type in {"decimal", "numeric"}:
            return f"{data_type}({column.precision},{column.scale})"
        if data_type in {"datetime2", "datetimeoffset", "time"}:
            return f"{data_type}({column.scale})"
        return data_type

    @contextmanager
    def _identity_insert(self, table: TableRef, enabled: bool):
        cursor = self.connection.cursor()
        if enabled:
            cursor.execute(f"SET IDENTITY_INSERT {quote_table(table)} ON")
        try:
            yield
        finally:
            if enabled:
                cursor.execute(f"SET IDENTITY_INSERT {quote_table(table)} OFF")
