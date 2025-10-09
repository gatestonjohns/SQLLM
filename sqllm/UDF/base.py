from __future__ import annotations

from abc import ABC, abstractmethod
import duckdb


class BaseUDF(ABC):
    """
    Abstract base for per-row scalar UDFs registered with DuckDB.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The DuckDB function name (e.g., 'llm_row')."""
        ...

    @abstractmethod
    def register(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Register this UDF on the provided DuckDB connection."""
        ...
