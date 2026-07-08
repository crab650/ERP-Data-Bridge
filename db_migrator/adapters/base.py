from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence


@dataclass(frozen=True)
class Column:
    name: str
    data_type: str
    max_length: int | None
    precision: int | None
    scale: int | None
    nullable: bool
    is_identity: bool = False
    is_computed: bool = False


@dataclass(frozen=True)
class TableRef:
    schema: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.schema}.{self.name}"


@dataclass(frozen=True)
class IndexColumn:
    name: str
    descending: bool = False


@dataclass(frozen=True)
class Index:
    name: str
    unique: bool
    type_desc: str
    key_columns: list[IndexColumn]
    included_columns: list[str] = field(default_factory=list)
    filter_definition: str | None = None


@dataclass
class TableSchema:
    table: TableRef
    columns: list[Column]
    primary_key: list[str] = field(default_factory=list)
    primary_key_type_desc: str | None = None
    indexes: list[Index] = field(default_factory=list)

    @property
    def insertable_columns(self) -> list[Column]:
        return [column for column in self.columns if not column.is_computed]


class DatabaseSource(ABC):
    @abstractmethod
    def list_tables(self) -> list[TableRef]:
        raise NotImplementedError

    @abstractmethod
    def get_table_schema(self, table: TableRef) -> TableSchema:
        raise NotImplementedError

    @abstractmethod
    def count_rows(self, table: TableRef, where_clause: str | None = None) -> int:
        raise NotImplementedError

    @abstractmethod
    def iter_rows(
        self,
        schema: TableSchema,
        batch_size: int,
        where_clause: str | None = None,
    ) -> Iterable[list[tuple[Any, ...]]]:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


class DatabaseTarget(ABC):
    @abstractmethod
    def prepare_table(self, schema: TableSchema, if_exists: str) -> bool:
        """Prepare target table and return whether data should be copied."""
        raise NotImplementedError

    @abstractmethod
    def insert_rows(
        self,
        schema: TableSchema,
        rows: Sequence[tuple[Any, ...]],
        preserve_identity: bool,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def create_indexes(self, schema: TableSchema) -> None:
        raise NotImplementedError

    @abstractmethod
    def count_rows(self, table: TableRef) -> int:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError
