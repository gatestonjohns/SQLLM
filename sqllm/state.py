import reflex as rx
import pandas as pd
import logging
from typing import Literal
from .backend.Engine.engine import Engine, TableRepresentationObject, ExecResult
from .backend.LLM.OpenAI import OpenAIProvider
import duckdb
import uuid

llm = OpenAIProvider()
engine = Engine(conn=duckdb.connect(":memory:"), llm=llm)

ExecutionTaskType = Literal["EDITOR", "PDF_TO_TABLE", "SMART_JOIN", "SMART_JOIN_TEST"]

class ExecutionTask(rx.Base):
    """ExecutionTask is a single execution task for a SQL query."""
    id: uuid.UUID
    sql: str
    summary: str
    type: ExecutionTaskType
    percent_done: int = 0
    result: ExecResult | None = None
    error: Exception | None = None
    warnings: list[str] = []

    async def execute_async(self, engine: Engine):
        """Execute query with more granular progress tracking.

        Yields: (progress: float, is_done: bool, result: ExecResult | None)
        """
        try:
            # Consume the engine's async generator
            async for percent_done, is_done, result in engine.execute(self.sql):
                self.percent_done = percent_done

                # Handle completion with result
                if is_done and result is not None:
                    self.result = result
                    self.warnings = result.warnings

                # Yield progress tuple to propagate to frontend
                yield (percent_done, is_done, result)

        except Exception as e:
            self.error = e
            self.percent_done = 100
            yield (100, True, None)



class State(rx.State):
    """State management for the SQL editor."""

    execution_tasks: list[ExecutionTask] = []
    latest_results_df: pd.DataFrame = pd.DataFrame()

    available_tables: list[TableRepresentationObject] = []
    available_pdfs: list[str] = []

    # Total LLM token/cost
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    task_count: int = 0

    @rx.event(background=True)
    async def submit_execution_task(self, type: ExecutionTaskType, sql: str, summary: str):
        """Submit an execution task for the SQL query."""
        task = ExecutionTask(id=uuid.uuid4(), type=type, sql=sql, summary=summary)

        # Add task to state and show it immediately
        async with self:
            self.execution_tasks.insert(0, task)
        yield

        # Consume the async generator and update progress
        async for progress, is_done, result in task.execute_async(engine):
            async with self:
                self.execution_tasks = self.execution_tasks.copy()
            yield  # Push state update to frontend

            # Check for errors after each iteration, especially when task completes
            if task.error is not None:
                # Log the error for debugging
                logging.error(f"Task execution failed: {task.error}")
                # Frontend will see the error via task.error field in execution_tasks
                break
        
        # Task finished, update the results and availabletables section
        async with self:
            self.latest_results_df = task.result.df
            self.available_tables = engine.list_tables()

    @rx.event
    def update_available_tables(self):
        """Update the available tables."""
        self.available_tables = engine.list_tables()

    @rx.event
    def add_available_pdf(self, file_path: str):
        """Add a new available PDF."""
        if file_path not in self.available_pdfs:
            self.available_pdfs.append(file_path)

    @rx.event
    def show_specific_results(self, task_id: str):
        """Show the results of a specific execution task."""
        print(f"exec task ids: {[task.id for task in self.execution_tasks]}")
        for task in self.execution_tasks:
            if str(task.id) == task_id:
                print(f"showing results for task {task.id}")
                print(f"task result df: {task.result.df}")
                self.latest_results_df = task.result.df
                break

    # @rx.var
    # def results_present(self) -> bool:
    #     """Check if there are results to display."""
    #     return not self.query_results_df.empty

    # @rx.var
    # def cumulative_total_tokens(self) -> int:
    #     """Get total tokens (input + output) for session."""
    #     return self.cumulative_input_tokens + self.cumulative_output_tokens

    # @rx.var
    # def current_query_total_tokens(self) -> int:
    #     """Get total tokens (input + output) for current query."""
    #     return self.current_query_input_tokens + self.current_query_output_tokens

    # def _update_token_stats(self):
    #     """Update token/cost statistics from LLM provider to trigger re-render."""
    #     session_stats = self._llm.get_session_stats()
    #     self.cumulative_input_tokens = session_stats["total_input_tokens"]
    #     self.cumulative_output_tokens = session_stats["total_output_tokens"]
    #     self.cumulative_cost = session_stats["total_cost"]
    #     self.query_count = session_stats["query_count"]

    #     query_stats = self._llm.get_current_query_stats()
    #     self.current_query_input_tokens = query_stats["input_tokens"]
    #     self.current_query_output_tokens = query_stats["output_tokens"]
    #     self.current_query_cost = query_stats["cost"]

    # @rx.event
    # def set_export_filename(self, filename: str):
    #     """Set the export filename."""
    #     self.export_filename = filename

    # @rx.var
    # def result_count(self) -> str:
    #     """Get the count of rows and columns in the results."""
    #     if self.query_results_df.empty:
    #         return ""
    #     return f"{len(self.query_results_df)} rows ☓ {len(self.query_results_df.columns)} columns"

    # def _reset_before_query_execution(self):
    #     """Reset the state before executing a query."""
    #     self.show_results = True
    #     self.error_message = ""
    #     self.success_message = ""
    #     self.query_results_df = pd.DataFrame()

    # @rx.event
    # def open_export_dialog(self):
    #     """Open the export dialog."""
    #     self.export_dialog_open = True

    # @rx.event
    # def close_export_dialog(self):
    #     """Close the export dialog."""
    #     self.export_dialog_open = False

    # @rx.event
    # def toggle_export_dialog_open(self, value: bool):
    #     """Toggle the export dialog open state."""
    #     self.export_dialog_open = value

    # def _execute_query_blocking(self, sql_query: str) -> tuple:
    #     """Execute query and list tables synchronously (runs in thread pool)."""
    #     result = self._engine.execute(sql_query)
    #     tables = self._engine.list_tables()
    #     return result, tables

    # @rx.event(background=True)
    # async def execute_query(self, sql_query: str, show_results: bool = True):
    #     """Execute the SQL query and update results."""
    #     try:
    #         # Step 1: Set loading state and notify frontend
    #         async with self:
    #             self._reset_before_query_execution()
    #             self._llm.reset_current_query_stats()
    #             self.is_loading = True
    #         yield  # Push loading state to frontend immediately

    #         # Step 2: Run blocking database operations in thread pool
    #         loop = asyncio.get_event_loop()
    #         with ThreadPoolExecutor() as executor:
    #             result, tables = await loop.run_in_executor(
    #                 executor, self._execute_query_blocking, sql_query
    #             )

    #         # Note: Debug sleep removed - if needed for testing, use:
    #         # await asyncio.sleep(300)  # Non-blocking alternative

    #         # Step 3: Update state with results and notify frontend
    #         async with self:
    #             self.show_results = show_results
    #             self.query_results_df = result.df
    #             self.available_tables = tables

    #             # Update token stats to trigger re-render
    #             self._update_token_stats()

    #             self.is_loading = False

    #             if result.warnings:
    #                 self.success_message = "Query executed with warnings."
    #             else:
    #                 self.success_message = "Query executed successfully."
    #         # Automatically yields when exiting context

    #         logging.info(
    #             f"Query executed successfully: {len(self.query_results_df)} rows returned"
    #         )

    #     except Exception as e:
    #         async with self:
    #             self.is_loading = False
    #             self.error_message = f"Error: {str(e)}"
    #         logging.error(f"✗ Query error: {e}")

    # @rx.event
    # async def handle_csv_upload(self, files: list[rx.UploadFile]):
    #     """Handle CSV file upload and load into DuckDB."""
    #     for file in files:
    #         try:
    #             self._reset_before_query_execution()

    #             # Read the uploaded file
    #             upload_data = await file.read()

    #             # Save temporarily to process with DuckDB
    #             upload_dir = rx.get_upload_dir()
    #             file_path = os.path.join(upload_dir, file.filename)

    #             with open(file_path, "wb") as f:
    #                 f.write(upload_data)

    #             # Run blocking DuckDB operation in thread pool
    #             loop = asyncio.get_event_loop()
    #             with ThreadPoolExecutor() as executor:
    #                 (
    #                     created_table_name,
    #                     created_table_exec_result,
    #                 ) = await loop.run_in_executor(
    #                     executor, self._engine.load_csv, file_path
    #                 )

    #             self.query_results_df = created_table_exec_result.df

    #             # Update available tables list
    #             self.available_tables = self._engine.list_tables()

    #             self.success_message = f"Successfully loaded {file.filename} as table '{created_table_name}'"
    #             logging.info(
    #                 f"Loaded {file.filename} into DuckDB as table '{created_table_name}'"
    #             )

    #         except Exception as e:
    #             self.error_message = f"Error uploading {file.filename}: {str(e)}"
    #             logging.error(f"✗ Error uploading {file.filename}: {e}")

    # @rx.event
    # async def handle_pdf_upload(self, files: list[rx.UploadFile]):
    #     """Handle PDF upload and store on disk for later ingestion."""
    #     for file in files:
    #         try:
    #             self._reset_before_query_execution()

    #             upload_data = await file.read()

    #             upload_dir = rx.get_upload_dir()
    #             pdf_dir = os.path.join(upload_dir, "pdfs")
    #             os.makedirs(pdf_dir, exist_ok=True)
    #             file_path = os.path.join(pdf_dir, file.filename)

    #             with open(file_path, "wb") as f:
    #                 f.write(upload_data)

    #             if file_path not in self.available_pdfs:
    #                 self.available_pdfs.append(file_path)

    #             self.success_message = (
    #                 f"Stored PDF {file.filename}. Use its path in llm_pdf_to_table()."
    #             )
    #             logging.info("Stored PDF %s at %s", file.filename, file_path)

    #         except Exception as e:
    #             self.error_message = f"Error uploading {file.filename}: {str(e)}"
    #             logging.error(f"✗ Error uploading {file.filename}: {e}")
    #             return

    # @rx.event
    # def export_results(self):
    #     """Export query results as CSV file."""
    #     try:
    #         if self.query_results_df.empty:
    #             self.error_message = "No results to export. Run a query first."
    #             return

    #         # Convert DataFrame to CSV string
    #         csv_data = self.query_results_df.to_csv(index=False)

    #         self.success_message = (
    #             f"Results exported successfully ({len(self.query_results_df)} rows)"
    #         )
    #         logging.info(f"Exported {len(self.query_results_df)} rows")

    #         properly_extended_filename = (
    #             self.export_filename
    #             if self.export_filename.endswith(".csv")
    #             else self.export_filename + ".csv"
    #         )

    #         # Trigger download by passing data directly
    #         return rx.download(data=csv_data, filename=properly_extended_filename)

    #     except Exception as e:
    #         self.error_message = f"Error exporting results: {str(e)}"
    #         logging.error(f"✗ Error exporting: {e}")
