from __future__ import annotations
import duckdb
import pandas as pd
from dataclasses import dataclass
import sqlglot
import re
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

    def execute(self, sql: str) -> ExecResult:
        trees = sqlglot.parse(sql, read="duckdb")

        if len(trees) > 1:
            raise ValueError("Only one SQL statement can be executed at a time.")

        tree = trees[0]
        warnings: list[str] = []
        calls: list[VTFCall] = []
        for handler in self.handlers:
            calls.extend(handler.discover(tree))

        for call in calls:
            table_name = call.handler.materialize(call, self)
            call.rewrite_to_table(table_name)

        rewritten_sql = tree.sql(dialect="duckdb")
        df = self.conn.execute(rewritten_sql).fetchdf()
        return ExecResult(df=df, warnings=warnings)

    def _materialize_df(self, df: pd.DataFrame, table_name: str) -> None:
        self.conn.register(f"__reg_{table_name}", df)
        self.conn.execute(
            f"CREATE OR REPLACE TEMP TABLE {table_name} AS SELECT * FROM __reg_{table_name}"
        )
        self.conn.unregister(f"__reg_{table_name}")

    def _generate_new_table_name(self, raw_string: str) -> str:
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
        if new_table_name in existing_table_names:
            int_suffix: int = 1
            base_name = new_table_name
            proposed_name = f"{base_name}_{int_suffix}"

            while proposed_name in existing_table_names:
                int_suffix += 1
                proposed_name = f"{base_name}_{int_suffix}"

            new_table_name = proposed_name

        return new_table_name

    def _get_existing_table_names(self) -> list[str]:
        """Get a list of all table names currently in the database."""
        return [row[0] for row in self.conn.execute("SHOW TABLES").fetchall()]

    def load_csv(self, file_path: str) -> tuple[str, ExecResult]:
        """Load a CSV file into a DuckDB table and return the dataframe of the loaded table."""
        cleaned_table_name = self._generate_new_table_name(
            file_path.split("/")[-1].split(".")[0]
        )

        self.conn.execute(
            f"CREATE OR REPLACE TABLE {cleaned_table_name} AS SELECT * FROM read_csv_auto('{file_path}', header=true)"
        )

        df = self.conn.execute(f"SELECT * FROM {cleaned_table_name}").fetchdf()

        return cleaned_table_name, ExecResult(df=df, warnings=[])

    def list_tables(self) -> list[TableRepresentationObject]:
        """Get a list of TableRepresentationObjects for all tables currently in the database."""
        table_representation_objects: list[TableRepresentationObject] = []
        all_existing_table_names: list[str] = self._get_existing_table_names()

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
