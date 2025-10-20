import duckdb
from .base import BaseUDF
from .llm import LLMUDF

ACTIVE_SCALAR_UDFS: list[type[BaseUDF]] = [LLMUDF]


def register_all_udfs(db_connection: duckdb.DuckDBPyConnection, **kwargs) -> None:
    """Bind all UDFs from ACTIVE_SCALAR_UDFS to the DuckDB connection."""
    for udf in ACTIVE_SCALAR_UDFS:
        udf(**kwargs).register(db_connection)
