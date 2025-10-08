import duckdb
from .base import BaseUDF
from .llm import LLMUDF

BaseUDF.REGISTRY.append(LLMUDF())

def register_all_udfs(db_connection: duckdb.DuckDBPyConnection) -> None:
    """Bind all UDFs from the BaseUDF.REGISTRY to the DuckDB connection."""
    BaseUDF.register_all(db_connection)


__all__ = ["register_all_udfs"]
