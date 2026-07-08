import datetime
import decimal
import os
import sqlite3
from typing import Any, Sequence

from .base import Column, DatabaseTarget, Index, TableRef, TableSchema

# Register adapters for non-standard SQLite types
sqlite3.register_adapter(decimal.Decimal, lambda d: float(d))
sqlite3.register_adapter(datetime.time, lambda t: t.isoformat())


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def get_table_name(table: TableRef) -> str:
    if not table.schema or table.schema.lower() == "dbo":
        return table.name
    return f"{table.schema}_{table.name}"


def quote_table(table: TableRef) -> str:
    return quote_ident(get_table_name(table))


class SqliteTarget(DatabaseTarget):
    def __init__(self, config: dict[str, Any]) -> None:
        db_path = config.get("database")
        if not db_path:
            raise ValueError("SQLite configuration must specify a 'database' file path.")
        
        # Ensure the target directory exists
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
            
        self.connection = sqlite3.connect(db_path)
        
        # Performance optimizations for bulk inserts
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")

    def prepare_table(self, schema: TableSchema, if_exists: str) -> bool:
        if if_exists not in {"skip", "truncate", "recreate"}:
            raise ValueError("if_exists must be one of: skip, truncate, recreate")

        cursor = self.connection.cursor()
        table_name = quote_table(schema.table)
        exists = self._table_exists(schema.table)

        if exists and if_exists == "skip":
            return False
        if exists and if_exists == "truncate":
            cursor.execute(f"DELETE FROM {table_name}")
            self.connection.commit()
            return True
        if exists and if_exists == "recreate":
            cursor.execute(f"DROP TABLE {table_name}")
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
        table_name = quote_table(schema.table)
        sql = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"

        cursor = self.connection.cursor()
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
        table_name = quote_table(table)
        row = cursor.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        return int(row[0])

    def close(self) -> None:
        self.connection.close()

    def _table_exists(self, table: TableRef) -> bool:
        cursor = self.connection.cursor()
        table_name = get_table_name(table)
        row = cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        ).fetchone()
        return row is not None

    def _build_create_table_sql(self, schema: TableSchema) -> str:
        column_defs = []
        pk_in_column_def = False
        
        # If there is a single primary key and that column is an identity column,
        # we can define it as INTEGER PRIMARY KEY AUTOINCREMENT in SQLite.
        has_single_pk_identity = (
            len(schema.primary_key) == 1
            and any(c.name == schema.primary_key[0] and c.is_identity for c in schema.columns)
        )
        
        for column in schema.columns:
            if column.is_computed:
                raise ValueError(
                    f"Computed column {column.name} is not supported for SQLite CREATE TABLE."
                )
                
            parts = [quote_ident(column.name), self._format_type(column)]
            
            if has_single_pk_identity and column.name == schema.primary_key[0]:
                parts[1] = "INTEGER"
                parts.append("PRIMARY KEY AUTOINCREMENT")
                pk_in_column_def = True
            
            parts.append("NULL" if column.nullable else "NOT NULL")
            column_defs.append(" ".join(parts))
            
        if schema.primary_key and not pk_in_column_def:
            pk_cols = ", ".join(quote_ident(col) for col in schema.primary_key)
            column_defs.append(f"PRIMARY KEY ({pk_cols})")
            
        body = ",\n    ".join(column_defs)
        table_name = quote_table(schema.table)
        return f"CREATE TABLE {table_name} (\n    {body}\n)"

    def _build_create_index_sql(self, table: TableRef, index: Index) -> str:
        unique = "UNIQUE " if index.unique else ""
        key_columns = ", ".join(
            f"{quote_ident(column.name)} {'DESC' if column.descending else 'ASC'}"
            for column in index.key_columns
        )
        filter_clause = f" WHERE {index.filter_definition}" if index.filter_definition else ""
        
        # SQLite index names must be unique database-wide, so prepend the table name
        table_name_clean = get_table_name(table)
        index_name = quote_ident(f"IX_{table_name_clean}_{index.name}")
        
        return (
            f"CREATE {unique}INDEX IF NOT EXISTS {index_name} "
            f"ON {quote_table(table)} ({key_columns}){filter_clause}"
        )

    def _format_type(self, column: Column) -> str:
        data_type = column.data_type.lower()
        if data_type in {"int", "bigint", "smallint", "tinyint", "bit"}:
            return "INTEGER"
        if data_type in {"decimal", "numeric", "float", "real", "money", "smallmoney"}:
            return "REAL"
        if data_type in {
            "varchar", "nvarchar", "char", "nchar", "text", "ntext",
            "datetime", "datetime2", "date", "time", "smalldatetime", "datetimeoffset",
            "uniqueidentifier", "xml"
        }:
            return "TEXT"
        if data_type in {"binary", "varbinary", "image", "timestamp", "rowversion"}:
            return "BLOB"
        return "TEXT"
