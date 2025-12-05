from __future__ import annotations
from duckdb import DuckDBPyConnection
import pandas as pd
from dataclasses import dataclass
import sqlglot
import re
import asyncio
from typing import AsyncIterator
from ..LLM.base import LLMProvider
from ..LLM import context as llm_context
from ..VTF.base import VTFCall
from ..VTF.register import get_vtf_handlers
from ..UDF.register import register_all_udfs
from ...models.execution_task import ExecResult
from ...models.token_usage import TokenUsage
from .progress import ProgressTracker


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
    """
    The top level object for performing SQL and LLM powered operations.
    """

    def __init__(
        self,
        conn: DuckDBPyConnection,
        llm: LLMProvider,
    ):
        """
        Initialize the Engine. Also brings all VTFs into scope and registers all UDFs.

        Args:
            conn: The DuckDB database connection object
            llm: The LLM provider object
        """
        self.conn = conn
        self.llm = llm
        self.handlers = get_vtf_handlers()
        register_all_udfs(self.conn, llm_provider=self.llm)
        self.active_tasks: dict[str, asyncio.Task] = {}

    def _register_task(self, task_id: str, task: asyncio.Task) -> None:
        """Register a task by its ID."""
        self.active_tasks[task_id] = task

    def _unregister_task(self, task_id: str) -> None:
        """Unregister a task by its ID."""
        if task_id in self.active_tasks:
            del self.active_tasks[task_id]

    def cancel_task(self, task_id: str) -> None:
        """Cancel a running task by its ID."""
        if task_id in self.active_tasks:
            self.active_tasks[task_id].cancel()

    async def execute(
        self, task_id: str, sql: str
    ) -> AsyncIterator[tuple[int, bool, ExecResult | None, TokenUsage | None]]:
        """
        Execute SQL with granular progress reporting via asyncio.Queue.
        """
        queue = asyncio.Queue()

        # Helper to push updates to the queue
        def on_progress(p: float):
            queue.put_nowait(int(p))

        # Create root tracker
        tracker = ProgressTracker(on_update=on_progress)

        async def worker():
            try:
                # Run the heavy execution pipeline
                result = await self._run_execution_pipeline(sql, tracker)
                queue.put_nowait(result)  # Push the final result tuple
            except asyncio.CancelledError:
                # Signal cancellation specifically so the frontend can handle it nicely
                queue.put_nowait(Exception("Task was cancelled"))
            except Exception as e:
                queue.put_nowait(e)  # Push exception to be raised in main loop
            finally:
                queue.put_nowait(None)  # Sentinel to signal completion
                self._unregister_task(task_id)

        # Start the heavy execution in the background
        execution_task = asyncio.create_task(worker())
        self._register_task(task_id, execution_task)

        last_yielded_progress = 0

        # Loop indefinitely reading from the queue until sentinel (None) is received
        while True:
            item = await queue.get()

            # Sentinel value means execution is finished
            if item is None:
                break

            # If item is an Exception, re-raise it here
            if isinstance(item, Exception):
                raise item

            # If item is the final result tuple (100, True, result, usage)
            if isinstance(item, tuple) and len(item) == 4 and item[1] is True:
                yield item
                break

            # If item is progress update (int)
            if isinstance(item, int):
                # Ensure progress is monotonic or at least update only on change
                if item != last_yielded_progress:
                    print(f"Engine Debug: Yielding progress {item}")
                    yield (item, False, None, None)
                    last_yielded_progress = item

            # Also handle if _run_execution_pipeline yields intermediate tuples (unlikely with current code but safe)
            elif isinstance(item, tuple):
                yield item

    async def _run_execution_pipeline(
        self, sql: str, tracker: ProgressTracker
    ) -> tuple[int, bool, ExecResult | None, TokenUsage | None]:
        """
        Internal execution logic that updates the provided ProgressTracker.
        """
        warnings: list[str] = []
        task_total_usage = llm_context.init_usage()

        # Define Phases
        # 1. Parsing (5%)
        # 2. VTF Discovery (5%)
        # 3. VTF Materialization (75%)
        # 4. DuckDB Execution (15%)
        phase_parsing = tracker.add_phase("Parsing", 0.05)
        phase_discovery = tracker.add_phase("Discovery", 0.05)
        phase_materialization = tracker.add_phase("Materialization", 0.75)
        phase_execution = tracker.add_phase("Execution", 0.15)

        # Phase 1: Parsing
        phase_parsing.set_total(1)
        trees = sqlglot.parse(sql, read="duckdb")
        if not trees:
            raise ValueError("No valid SQL statements provided.")
        phase_parsing.increment()

        # Phase 2: VTF Discovery
        # We don't know exactly how many calls yet, but discovery itself is quick.
        # Let's just treat it as one unit of work per tree for simplicity.
        phase_discovery.set_total(len(trees))

        all_vtf_calls: list[tuple[int, VTFCall, sqlglot.Expression]] = []
        for i, tree in enumerate(trees):
            calls: list[VTFCall] = []
            for handler in self.handlers:
                calls.extend(handler.discover(tree))
            for call in calls:
                all_vtf_calls.append((i, call, tree))
            phase_discovery.increment()

        # Phase 3: VTF Materialization
        total_vtf_count = len(all_vtf_calls)
        phase_materialization.set_total(total_vtf_count)

        if total_vtf_count > 0:
            for vtf_index, (stmt_index, call, tree) in enumerate(all_vtf_calls):
                # Create a sub-tracker for this specific VTF call if desired,
                # or just pass the materialization phase tracker and let it handle sub-progress?
                # Better: Create a sub-tracker for THIS specific VTF call.
                # We give each VTF call equal weight within the materialization phase for now.
                vtf_tracker = phase_materialization.add_phase(
                    f"VTF_{vtf_index}", 1.0 / total_vtf_count
                )

                # Execute Materialization
                table_name = await call.handler.materialize(call, self, vtf_tracker)
                call.rewrite_to_table(table_name)

                # Ensure this VTF's tracker is marked complete if the handler didn't do it
                if (
                    vtf_tracker.completed_work < vtf_tracker.total_work
                    or vtf_tracker.total_work == 0
                ):
                    vtf_tracker.set_total(1)
                    vtf_tracker.increment()
        else:
            # If no VTFs, mark phase as done
            phase_materialization.set_total(1)
            phase_materialization.increment()

        # Phase 4: DuckDB Execution
        phase_execution.set_total(len(trees))
        df: pd.DataFrame | None = None

        for i, tree in enumerate(trees):
            rewritten_sql = tree.sql(dialect="duckdb")
            print(f"rewritten_sql (statement {i + 1}/{len(trees)}):", rewritten_sql)

            # Execute the statement
            result = self.conn.execute(rewritten_sql)

            # Store the result (we'll return the last one)
            df = result.fetchdf()
            phase_execution.increment()

        # Only print the final result
        print("df:", df.head())

        # Ensure we hit 100% at the end
        # (The tracker callback logic handles intermediate updates, but we return the final payload here)
        return (100, True, ExecResult(df=df, warnings=warnings), task_total_usage)

    def _materialize_df(
        self, df: pd.DataFrame, table_name: str, temporary: bool = True
    ):
        """
        Materialize a DataFrame into a DuckDB table.
        Essentially creates a (temporary) DuckDB table in the database from the provided DataFrame.

        Args:
            df (pd.DataFrame): The DataFrame to materialize
            table_name (str): The name of the table to materialize the DataFrame into
            temporary (bool): Whether the table should be temporary
        """
        temp_df_table_name = f"__reg_{table_name}"
        self.conn.register(temp_df_table_name, df)
        self.conn.execute(
            f"CREATE OR REPLACE {'TEMP' if temporary else ''} TABLE {table_name} AS SELECT * FROM {temp_df_table_name}"
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

        print(
            "all_existing_table_names from list_tables: ",
            self._get_existing_table_names(),
        )

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
