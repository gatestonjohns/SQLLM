from __future__ import annotations
import duckdb
import pandas as pd
from dataclasses import dataclass
import sqlglot
import re
from typing import AsyncIterator
from ..LLM.OpenAI import OpenAIProvider
from ..VTF.base import VTFCall
from ..VTF.register import get_vtf_handlers
from ..UDF.register import register_all_udfs


@dataclass(frozen=True)
class ExecResult:
    df: pd.DataFrame
    warnings: list[str]


@dataclass(frozen=True)
class TableColumnRepresentationObject:
    name: str
    type: str


@dataclass(frozen=True)
class TableRepresentationObject:
    name: str
    columns: list[TableColumnRepresentationObject]
    row_count: int


class Engine:
    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        llm: OpenAIProvider,
    ):
        self.conn = conn
        self.llm = llm
        self.handlers = get_vtf_handlers()
        register_all_udfs(self.conn, llm_provider=self.llm)

    async def execute(self, sql: str) -> AsyncIterator[tuple[int, bool, ExecResult | None]]:
        warnings: list[str] = []

        # Phase 1: Parsing (0-5%)
        yield (0, False, None)

        trees = sqlglot.parse(sql, read="duckdb")

        if not trees:
            raise ValueError("No valid SQL statements provided.")

        yield (5, False, None)

        df: pd.DataFrame | None = None  # Will store the result of the last statement

        # Phase 2: VTF Discovery (5-10%)
        all_vtf_calls: list[tuple[int, VTFCall, sqlglot.Expression]] = []
        for i, tree in enumerate(trees):
            calls: list[VTFCall] = []
            for handler in self.handlers:
                calls.extend(handler.discover(tree))
            for call in calls:
                all_vtf_calls.append((i, call, tree))

        yield (10, False, None)

        # Phase 3: VTF Materialization (10-85%)
        total_vtf_count = len(all_vtf_calls)
        if total_vtf_count > 0:
            for vtf_index, (stmt_index, call, tree) in enumerate(all_vtf_calls):
                progress = 10 + int(((vtf_index + 1) / total_vtf_count) * 75)
                yield (progress, False, None)

                table_name = await call.handler.materialize(call, self)
                call.rewrite_to_table(table_name)

        yield (85, False, None)

        # Phase 4: DuckDB Execution (85-100%)
        total_stmt_count = len(trees)
        for i, tree in enumerate(trees):
            if total_stmt_count > 0:
                progress = 85 + int(((i + 1) / total_stmt_count) * 15)
                yield (progress, False, None)

            rewritten_sql = tree.sql(dialect="duckdb")
            print(f"rewritten_sql (statement {i + 1}/{len(trees)}):", rewritten_sql)

            # Execute the statement
            result = self.conn.execute(rewritten_sql)

            # Store the result (we'll return the last one)
            df = result.fetchdf()

        # Only print the final result
        print("df:", df.head())

        yield (100, True, ExecResult(df=df, warnings=warnings))

    def _materialize_df(self, df: pd.DataFrame, table_name: str, temporary: bool = True) -> None:
        temp_df_table_name = f"__reg_{table_name}"
        self.conn.register(temp_df_table_name, df)
        self.conn.execute(
            f"CREATE OR REPLACE {"TEMP" if temporary else ""} TABLE {table_name} AS SELECT * FROM {temp_df_table_name}"
        )
        self.conn.unregister(temp_df_table_name)

    def _generate_new_table_name(self, raw_string: str, ensure_new: bool = True) -> str:
        """
        Generate a new unique, clean, SQL-friendly table name from a raw string by enforcing:
        - is unique among existing table names
        - only alphanumeric and underscore characters
        - starts with a letter or underscore (not a digit)
        """
        new_table_name = re.sub(r"\W+", "_", raw_string)

        if not re.match(r"^[A-Za-z_]", new_table_name):
            new_table_name = f"_{new_table_name}"

        existing_table_names = self._get_existing_table_names()
        if ensure_new and new_table_name in existing_table_names:
            int_suffix: int = 1
            base_name = new_table_name
            proposed_name = f"{base_name}_{int_suffix}"

            while proposed_name in existing_table_names:
                int_suffix += 1
                proposed_name = f"{base_name}_{int_suffix}"

            new_table_name = proposed_name

        return new_table_name

    def _get_existing_table_names(self, include_temp: bool = False) -> list[str]:
        """Get a list of all table names currently in the database."""
        return [
            row[0]
            for row in self.conn.execute(
                "SELECT table_name FROM duckdb_tables WHERE database_name = 'memory';"
            ).fetchall()
        ]

    def load_csv(self, file_path: str) -> tuple[str, ExecResult]:
        """Load a CSV file into a DuckDB table and return the dataframe of the loaded table."""
        cleaned_table_name = self._generate_new_table_name(
            file_path.split("/")[-1].split(".")[0]
        )

        self.conn.execute(
            f"CREATE OR REPLACE TABLE {cleaned_table_name} AS FROM read_csv('{file_path}',  header = true, normalize_names = true)"
        )

        df = self.conn.execute(f"SELECT * FROM {cleaned_table_name}").fetchdf()

        print("df: ", df.head())
        print("cleaned_table_name: ", cleaned_table_name)

        print("all_existing_table_names from list_tables: ", self._get_existing_table_names())

        return cleaned_table_name, ExecResult(df=df, warnings=[])

    def list_tables(
        self, include_temp: bool = False
    ) -> list[TableRepresentationObject]:
        """Get a list of TableRepresentationObjects for all tables currently in the database."""
        table_representation_objects: list[TableRepresentationObject] = []
        all_existing_table_names: list[str] = self._get_existing_table_names(
            include_temp=include_temp
        )

        print("all_existing_table_names from list_tables: ", all_existing_table_names)

        for table_name in all_existing_table_names:
            columns = [
                TableColumnRepresentationObject(name=row[0], type=row[1])
                for row in self.conn.execute(f"DESCRIBE {table_name}").fetchall()
            ]
            row_count = self.conn.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]
            table_representation_objects.append(
                TableRepresentationObject(
                    name=table_name,
                    columns=columns,
                    row_count=row_count,
                )
            )

        return table_representation_objects
