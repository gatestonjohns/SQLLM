from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List
import duckdb


class BaseUDF(ABC):
    """
    Abstract base for per-row scalar UDFs registered with DuckDB.
    """

    REGISTRY: List[BaseUDF] = []

    @property
    @abstractmethod
    def name(self) -> str:
        """The DuckDB function name (e.g., 'llm_row')."""
        ...

    @abstractmethod
    def register(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Register this UDF against the provided DuckDB connection."""
        ...

    @staticmethod
    def register_all(conn: duckdb.DuckDBPyConnection) -> None:
        """Register all UDFs in REGISTRY against the provided DuckDB connection."""
        for udf in BaseUDF.REGISTRY:
            udf.register(conn)
