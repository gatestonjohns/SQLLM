import reflex as rx
import os
import pandas as pd
import logging
from .backend.Engine.engine import Engine, TableRepresentationObject
from .backend.LLM.OpenAI import OpenAIProvider
import duckdb

engine = Engine(
    conn=duckdb.connect(database=":memory:"),
    llm=OpenAIProvider(),
)


class State(rx.State):
    """State management for the SQL editor."""

    query_results_df: pd.DataFrame = pd.DataFrame()
    error_message: str = ""
    success_message: str = ""
    available_tables: list[TableRepresentationObject] = []
    available_pdfs: list[str] = []
    export_dialog_open: bool = False
    export_filename: str = "query_results.csv"
    is_loading: bool = False

    @rx.event
    def set_export_filename(self, filename: str):
        """Set the export filename."""
        self.export_filename = filename

    @rx.var
    def result_count(self) -> str:
        """Get the count of rows and columns in the results."""
        if self.query_results_df.empty:
            return ""
        return f"{len(self.query_results_df)} rows ☓ {len(self.query_results_df.columns)} columns"

    def _reset_before_query_execution(self):
        """Reset the state before executing a query."""
        self.error_message = ""
        self.success_message = ""
        self.query_results_df = pd.DataFrame()

    @rx.event
    def open_export_dialog(self):
        """Open the export dialog."""
        self.export_dialog_open = True

    @rx.event
    def close_export_dialog(self):
        """Close the export dialog."""
        self.export_dialog_open = False

    @rx.event
    def toggle_export_dialog_open(self, value: bool):
        """Toggle the export dialog open state."""
        self.export_dialog_open = value

    @rx.event
    def execute_query(self, sql_query: str):
        """Execute the SQL query and update results."""
        try:
            self._reset_before_query_execution()
            self.is_loading = True
            yield
            result = engine.execute(sql_query)
            self.query_results_df = result.df
            self.available_tables = engine.list_tables()

            logging.info(
                f"Query executed successfully: {len(self.query_results_df)} rows returned"
            )
            self.is_loading = False
            if result.warnings:
                self.success_message = "Query executed with warnings."
            else:
                self.success_message = "Query executed successfully."

        except Exception as e:
            self.is_loading = False
            self.error_message = f"Error: {str(e)}"
            logging.error(f"✗ Query error: {e}")

    @rx.event
    async def handle_csv_upload(self, files: list[rx.UploadFile]):
        """Handle CSV file upload and load into DuckDB."""
        for file in files:
            try:
                self._reset_before_query_execution()

                # Read the uploaded file
                upload_data = await file.read()

                # Save temporarily to process with DuckDB
                upload_dir = rx.get_upload_dir()
                file_path = os.path.join(upload_dir, file.filename)

                with open(file_path, "wb") as f:
                    f.write(upload_data)

                # Load into DuckDB and return the results
                created_table_name, created_table_exec_result = engine.load_csv(
                    file_path=file_path
                )
                self.query_results_df = created_table_exec_result.df

                # Update available tables list
                self.available_tables = engine.list_tables()

                self.success_message = f"Successfully loaded {file.filename} as table '{created_table_name}'"
                logging.info(
                    f"Loaded {file.filename} into DuckDB as table '{created_table_name}'"
                )

            except Exception as e:
                self.error_message = f"Error uploading {file.filename}: {str(e)}"
                logging.error(f"✗ Error uploading {file.filename}: {e}")

    @rx.event
    async def handle_pdf_upload(self, files: list[rx.UploadFile]):
        """Handle PDF upload and store on disk for later ingestion."""
        for file in files:
            try:
                self._reset_before_query_execution()

                upload_data = await file.read()

                upload_dir = rx.get_upload_dir()
                pdf_dir = os.path.join(upload_dir, "pdfs")
                os.makedirs(pdf_dir, exist_ok=True)
                file_path = os.path.join(pdf_dir, file.filename)

                with open(file_path, "wb") as f:
                    f.write(upload_data)

                if file_path not in self.available_pdfs:
                    self.available_pdfs.append(file_path)

                self.success_message = (
                    f"Stored PDF {file.filename}. Use its path in llm_pdf_to_table()."
                )
                logging.info("Stored PDF %s at %s", file.filename, file_path)

            except Exception as e:
                self.error_message = f"Error uploading {file.filename}: {str(e)}"
                logging.error(f"✗ Error uploading {file.filename}: {e}")
                return

    @rx.event
    def export_results(self):
        """Export query results as CSV file."""
        try:
            if self.query_results_df.empty:
                self.error_message = "No results to export. Run a query first."
                return

            # Convert DataFrame to CSV string
            csv_data = self.query_results_df.to_csv(index=False)

            self.success_message = (
                f"Results exported successfully ({len(self.query_results_df)} rows)"
            )
            logging.info(f"Exported {len(self.query_results_df)} rows")

            properly_extended_filename = (
                self.export_filename
                if self.export_filename.endswith(".csv")
                else self.export_filename + ".csv"
            )

            # Trigger download by passing data directly
            return rx.download(data=csv_data, filename=properly_extended_filename)

        except Exception as e:
            self.error_message = f"Error exporting results: {str(e)}"
            logging.error(f"✗ Error exporting: {e}")
