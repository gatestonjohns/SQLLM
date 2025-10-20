import reflex as rx
from reflex_monaco import monaco
import os
import pandas as pd
from .config import DEFAULT_SQL_QUERY
import logging
from .Engine.engine import Engine, TableRepresentationObject
from .LLM.OpenAI import OpenAIProvider
import duckdb

# Initialize database connection at module level

engine = Engine(
    conn=duckdb.connect(database=":memory:"),
    llm=OpenAIProvider(),
)


class State(rx.State):
    """State management for the SQL editor."""

    sql_query: str = DEFAULT_SQL_QUERY
    query_results_df: pd.DataFrame = pd.DataFrame()
    error_message: str = ""
    success_message: str = ""
    available_tables: list[TableRepresentationObject] = []
    available_pdfs: list[str] = []
    upload_dialog_open: bool = False
    upload_dialog_mode: str = "csv"

    # Batch Task Manager state
    pdf_batch_selected_pdfs: list[str] = []
    pdf_batch_columns: list[dict[str, str]] = []
    pdf_batch_table_name: str = ""
    pdf_batch_prompt: str = ""
    pdf_batch_force_recreate: bool = False
    pdf_batch_include_source: bool = False

    @rx.var
    def result_count(self) -> str:
        """Get the count of rows and columns in the results."""
        if self.query_results_df.empty:
            return ""
        return f"{len(self.query_results_df)} rows ☓ {len(self.query_results_df.columns)} columns"

    @rx.var
    def available_duck_types(self) -> list[str]:
        """Get available DuckDB types for schema builder."""
        return [
            "TEXT",
            "VARCHAR",
            "INTEGER",
            "BIGINT",
            "DOUBLE",
            "BOOLEAN",
            "DATE",
            "TIMESTAMP",
        ]

    @rx.var
    def batch_can_run(self) -> bool:
        """Check if batch task can be executed."""
        return (
            bool(self.pdf_batch_table_name.strip())
            and len(self.pdf_batch_columns) > 0
            and len(self.pdf_batch_selected_pdfs) > 0
        )

    def _reset_before_query_execution(self):
        """Reset the state before executing a query."""
        self.error_message = ""
        self.success_message = ""
        self.query_results_df = pd.DataFrame()

    @rx.event
    def set_sql_query(self, sql_query: str):
        """Set the SQL query."""
        self.sql_query = sql_query

    @rx.event
    def open_upload_dialog_csv(self):
        """Open the upload dialog for CSV files."""
        self.upload_dialog_mode = "csv"
        self.upload_dialog_open = True

    @rx.event
    def open_upload_dialog_pdf(self):
        """Open the upload dialog for PDF files."""
        self.upload_dialog_mode = "pdf"
        self.upload_dialog_open = True

    @rx.event
    def close_upload_dialog(self):
        """Close the upload dialog."""
        self.upload_dialog_open = False

    @rx.event
    def toggle_upload_dialog_open(self, value: bool):
        """Set the upload dialog open state."""
        self.upload_dialog_open = value

    @rx.event
    def execute_query(self):
        """Execute the SQL query and update results."""
        try:
            self._reset_before_query_execution()
            result = engine.execute(self.sql_query)
            self.query_results_df = result.df
            self.available_tables = engine.list_tables()

            logging.info(
                f"Query executed successfully: {len(self.query_results_df)} rows returned"
            )
            if result.warnings:
                self.success_message = "Query executed with warnings."
            else:
                self.success_message = "Query executed successfully."

        except Exception as e:
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
                return

        # Close the dialog after all uploads complete successfully
        self.upload_dialog_open = False

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

        self.upload_dialog_open = False

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

            # Trigger download by passing data directly
            return rx.download(data=csv_data, filename="query_results.csv")

        except Exception as e:
            self.error_message = f"Error exporting results: {str(e)}"
            logging.error(f"✗ Error exporting: {e}")

    @rx.event
    def add_pdf_batch_column(self):
        """Add a new column to the batch schema."""
        self.pdf_batch_columns.append({"name": "", "type": "TEXT"})

    @rx.event
    def update_pdf_batch_column(self, index: int, field: str, value: str):
        """Update a column in the batch schema."""
        if 0 <= index < len(self.pdf_batch_columns):
            self.pdf_batch_columns[index][field] = value

    @rx.event
    def remove_pdf_batch_column(self, index: int):
        """Remove a column from the batch schema."""
        if 0 <= index < len(self.pdf_batch_columns):
            self.pdf_batch_columns.pop(index)

    @rx.event
    def toggle_pdf_selection(self, pdf_path: str):
        """Toggle PDF selection for batch processing."""
        if pdf_path in self.pdf_batch_selected_pdfs:
            self.pdf_batch_selected_pdfs.remove(pdf_path)
        else:
            self.pdf_batch_selected_pdfs.append(pdf_path)

    @rx.event
    async def run_pdf_batch_ingest(self):
        """Execute batch PDF ingestion into a single table."""
        try:
            self._reset_before_query_execution()

            # Validate inputs
            table_name = self.pdf_batch_table_name.strip()
            if not table_name:
                self.error_message = "Table name is required"
                return

            if not self.pdf_batch_columns:
                self.error_message = "At least one column must be defined"
                return

            if not self.pdf_batch_selected_pdfs:
                self.error_message = "At least one PDF must be selected"
                return

            # Build schema string
            schema_parts = []
            for col in self.pdf_batch_columns:
                col_name = col.get("name", "").strip()
                col_type = col.get("type", "TEXT").strip().upper()

                if not col_name:
                    self.error_message = "All columns must have a name"
                    return

                schema_parts.append(f"{col_name} {col_type}")

            # Add source_pdf column if requested and not already present
            has_source = any(
                col.get("name", "").lower() == "source_pdf"
                for col in self.pdf_batch_columns
            )
            if self.pdf_batch_include_source and not has_source:
                schema_parts.append("source_pdf TEXT")

            schema_str = ", ".join(schema_parts)

            # Build SQL query
            create_clause = (
                "CREATE OR REPLACE TABLE"
                if self.pdf_batch_force_recreate
                else "CREATE TABLE IF NOT EXISTS"
            )

            # Build SELECT statements for each PDF
            selects = []
            for pdf_path in self.pdf_batch_selected_pdfs:
                # Get basename for source column
                basename = os.path.basename(pdf_path)

                # Escape single quotes in path and prompt
                escaped_path = pdf_path.replace("'", "''")
                escaped_prompt = self.pdf_batch_prompt.replace("'", "''")

                # Build llm_pdf_to_table call
                if self.pdf_batch_prompt.strip():
                    llm_call = f"llm_pdf_to_table('{escaped_path}', '{schema_str}', '{escaped_prompt}')"
                else:
                    llm_call = f"llm_pdf_to_table('{escaped_path}', '{schema_str}')"

                # Build SELECT with optional source column
                if self.pdf_batch_include_source:
                    select_stmt = (
                        f"SELECT '{basename}' AS source_pdf, * FROM {llm_call}"
                    )
                else:
                    select_stmt = f"SELECT * FROM {llm_call}"

                selects.append(select_stmt)

            # Combine with UNION ALL
            union_query = " UNION ALL ".join(selects)

            # Final SQL statement
            sql = f"{create_clause} {table_name} AS {union_query}"

            # Format SQL for readability before storing in editor
            try:
                import sqlglot

                formatted_sql = sqlglot.parse_one(sql).sql(
                    dialect="duckdb", pretty=True
                )
                self.sql_query = formatted_sql
            except Exception as e:
                # Fallback to unformatted SQL if formatting fails
                logging.warning(f"Could not format SQL: {e}")
                self.sql_query = sql

            # Execute the query
            logging.info(
                f"Executing batch PDF ingestion: {len(self.pdf_batch_selected_pdfs)} PDFs -> table '{table_name}'"
            )
            engine.execute(sql)

            # Fetch the created table to show results
            fetch_result = engine.execute(f"SELECT * FROM {table_name}")
            self.query_results_df = fetch_result.df

            # Update available tables
            self.available_tables = engine.list_tables()

            row_count = len(self.query_results_df)
            self.success_message = f"Successfully created table '{table_name}' with {row_count} rows from {len(self.pdf_batch_selected_pdfs)} PDFs"
            logging.info(
                f"Batch ingestion complete: {row_count} rows in '{table_name}'"
            )

        except Exception as e:
            self.error_message = f"Error during batch ingestion: {str(e)}"
            logging.error(f"✗ Batch ingestion error: {e}")


def index():
    csv_upload_section = rx.vstack(
        rx.upload(
            rx.vstack(
                rx.icon("file-up", size=32, color="teal"),
                rx.button(
                    rx.icon("folder-open", size=16),
                    "Select CSV Files",
                    color_scheme="teal",
                    size="2",
                    variant="soft",
                ),
                rx.text(
                    "Drag and drop CSV files here or click to browse",
                    size="2",
                    color="gray",
                    align="center",
                ),
                align="center",
                spacing="3",
            ),
            id="csv_upload",
            multiple=True,
            accept={"text/csv": [".csv"]},
            max_files=5,
            border="2px dashed",
            border_color="teal",
            padding="2em",
            border_radius="12px",
            background="var(--teal-a2)",
            width="100%",
        ),
        rx.cond(
            rx.selected_files("csv_upload").length() > 0,
            rx.vstack(
                rx.text("Selected files:", weight="bold", size="2"),
                rx.vstack(
                    rx.foreach(
                        rx.selected_files("csv_upload"),
                        lambda file: rx.hstack(
                            rx.icon("file-text", size=16, color="teal"),
                            rx.text(file, size="2"),
                            spacing="2",
                            align="center",
                        ),
                    ),
                    spacing="2",
                    width="100%",
                ),
                spacing="2",
                width="100%",
                padding="1em",
                background="var(--gray-a2)",
                border_radius="8px",
            ),
        ),
        rx.button(
            rx.icon("upload", size=18),
            "Upload CSV Files",
            on_click=State.handle_csv_upload(rx.upload_files(upload_id="csv_upload")),
            size="3",
            color_scheme="teal",
            width="100%",
            cursor="pointer",
        ),
        spacing="4",
        width="100%",
    )

    pdf_upload_section = rx.vstack(
        rx.upload(
            rx.vstack(
                rx.icon("file-plus", size=32, color="purple"),
                rx.button(
                    rx.icon("folder-open", size=16),
                    "Select PDF Files",
                    color_scheme="purple",
                    size="2",
                    variant="soft",
                ),
                rx.text(
                    "Drag and drop PDF files here or click to browse",
                    size="2",
                    color="gray",
                    align="center",
                ),
                align="center",
                spacing="3",
            ),
            id="pdf_upload",
            multiple=True,
            accept={"application/pdf": [".pdf"]},
            max_files=5,
            border="2px dashed",
            border_color="purple",
            padding="2em",
            border_radius="12px",
            background="var(--purple-a2)",
            width="100%",
        ),
        rx.cond(
            rx.selected_files("pdf_upload").length() > 0,
            rx.vstack(
                rx.text("Selected files:", weight="bold", size="2"),
                rx.vstack(
                    rx.foreach(
                        rx.selected_files("pdf_upload"),
                        lambda file: rx.hstack(
                            rx.icon("file", size=16, color="purple"),
                            rx.text(file, size="2"),
                            spacing="2",
                            align="center",
                        ),
                    ),
                    spacing="2",
                    width="100%",
                ),
                spacing="2",
                width="100%",
                padding="1em",
                background="var(--gray-a2)",
                border_radius="8px",
            ),
        ),
        rx.button(
            rx.icon("upload", size=18),
            "Upload PDF Files",
            on_click=State.handle_pdf_upload(rx.upload_files(upload_id="pdf_upload")),
            size="3",
            color_scheme="purple",
            width="100%",
            cursor="pointer",
        ),
        spacing="4",
        width="100%",
    )

    upload_dialog = rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.dialog.title(
                    rx.cond(
                        State.upload_dialog_mode == "csv",
                        rx.hstack(
                            rx.icon("database", size=24, color="teal"),
                            "Import CSV Files",
                            spacing="2",
                            align="center",
                        ),
                        rx.hstack(
                            rx.icon("file-plus", size=24, color="purple"),
                            "Store PDF Files",
                            spacing="2",
                            align="center",
                        ),
                    )
                ),
                rx.dialog.description(
                    rx.cond(
                        State.upload_dialog_mode == "csv",
                        "Upload CSV files to query them with SQL. Each file becomes a DuckDB table.",
                        "Upload PDFs to store them on disk. Reference the saved path in llm_pdf_to_table().",
                    ),
                    size="2",
                    color="gray",
                ),
                rx.cond(
                    State.upload_dialog_mode == "csv",
                    csv_upload_section,
                    pdf_upload_section,
                ),
                spacing="4",
                width="100%",
            ),
            rx.flex(
                rx.dialog.close(
                    rx.button(
                        "Close",
                        on_click=State.close_upload_dialog,
                        color_scheme="gray",
                        variant="soft",
                        size="2",
                    ),
                ),
                spacing="3",
                margin_top="16px",
                justify="end",
            ),
            style={"max_width": "550px"},
        ),
        open=State.upload_dialog_open,
        on_open_change=State.toggle_upload_dialog_open,
    )

    # Available tables display
    tables_display = rx.card(
        rx.cond(
            State.available_tables.length() > 0,
            rx.vstack(
                rx.hstack(
                    rx.icon("table", size=20, color="blue"),
                    rx.text(
                        "Available Tables",
                        size="3",
                        weight="bold",
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.hstack(
                    rx.foreach(
                        State.available_tables,
                        lambda table: rx.popover.root(
                            rx.popover.trigger(
                                rx.badge(
                                    rx.icon("table-2", size=14),
                                    table.name,
                                    color_scheme="blue",
                                    variant="soft",
                                    size="2",
                                )
                            ),
                            rx.popover.content(
                                rx.vstack(
                                    rx.text(
                                        f"Rows: {table.row_count}",
                                        size="2",
                                        weight="medium",
                                    ),
                                    rx.table.root(
                                        rx.table.header(
                                            rx.table.row(
                                                rx.table.column_header_cell("Column"),
                                                rx.table.column_header_cell("Type"),
                                            )
                                        ),
                                        rx.table.body(
                                            rx.foreach(
                                                table.columns,
                                                lambda col: rx.table.row(
                                                    rx.table.cell(col.name),
                                                    rx.table.cell(col.type),
                                                ),
                                            )
                                        ),
                                        size="1",
                                    ),
                                    spacing="2",
                                    align="start",
                                ),
                                side="top",
                                align="start",
                                style={"min_width": "240px"},
                            ),
                        ),
                    ),
                    spacing="2",
                    align="center",
                    wrap="wrap",
                ),
                spacing="3",
                align="start",
            ),
            rx.hstack(
                rx.icon("info", size=20, color="gray"),
                rx.text(
                    "No tables loaded yet. Click 'Import CSV' to get started.",
                    size="2",
                    color="gray",
                ),
                spacing="2",
                align="center",
            ),
        ),
        variant="surface",
        size="2",
    )

    pdf_display = rx.card(
        rx.cond(
            State.available_pdfs.length() > 0,
            rx.vstack(
                rx.hstack(
                    rx.icon("file", size=20, color="purple"),
                    rx.text(
                        "Stored PDFs",
                        size="3",
                        weight="bold",
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.vstack(
                    rx.foreach(
                        State.available_pdfs,
                        lambda pdf: rx.code(pdf, size="2"),
                    ),
                    spacing="1",
                    align="start",
                    width="100%",
                ),
                spacing="3",
                align="start",
            ),
            rx.hstack(
                rx.icon("info", size=20, color="gray"),
                rx.text(
                    "Upload PDFs to reference their saved paths in llm_pdf_to_table().",
                    size="2",
                    color="gray",
                ),
                spacing="2",
                align="center",
            ),
        ),
        variant="surface",
        size="2",
    )

    # Monaco SQL Editor - bound to State.sql_query
    editor_section = rx.card(
        rx.vstack(
            rx.hstack(
                rx.hstack(
                    rx.icon("code", size=20, color="indigo"),
                    rx.text(
                        "SQL Query Editor",
                        size="4",
                        weight="bold",
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.button(
                    rx.icon("play", size=18),
                    "Run Query",
                    on_click=State.execute_query,
                    size="3",
                    color_scheme="indigo",
                    variant="solid",
                    cursor="pointer",
                ),
                spacing="2",
                align="center",
                justify="between",
                width="100%",
            ),
            monaco(
                default_language="sql",
                value=State.sql_query,
                on_change=State.set_sql_query,
                height="400px",
                width="100%",
            ),
            spacing="3",
        ),
        variant="classic",
        width="100%",
    )

    # Batch Task Manager UI
    gui_section = rx.card(
        rx.vstack(
            # Header with Run Button
            rx.hstack(
                rx.hstack(
                    rx.icon("layers", size=20, color="purple"),
                    rx.text(
                        "Batch PDF to Table Converter",
                        size="4",
                        weight="bold",
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.button(
                    rx.icon("play", size=18),
                    "Create Table from PDFs",
                    on_click=State.run_pdf_batch_ingest,
                    size="3",
                    color_scheme="purple",
                    variant="solid",
                    disabled=~State.batch_can_run,
                    cursor="pointer",
                ),
                spacing="2",
                align="center",
                justify="between",
                width="100%",
            ),
            # Horizontal layout for sub-cards
            rx.hstack(
                # Section 1: PDF Selection
                rx.card(
                    rx.vstack(
                        rx.hstack(
                            rx.icon("file", size=18, color="purple"),
                            rx.text("Select PDFs", size="3", weight="bold"),
                            rx.spacer(),
                            rx.badge(
                                f"{State.pdf_batch_selected_pdfs.length()} selected",
                                color_scheme="purple",
                                variant="soft",
                            ),
                            spacing="2",
                            align="center",
                            width="100%",
                        ),
                        rx.cond(
                            State.available_pdfs.length() > 0,
                            rx.vstack(
                                rx.foreach(
                                    State.available_pdfs,
                                    lambda pdf: rx.box(
                                        rx.checkbox(
                                            rx.text(pdf, size="2"),
                                            checked=State.pdf_batch_selected_pdfs.contains(
                                                pdf
                                            ),
                                            on_change=lambda _: State.toggle_pdf_selection(
                                                pdf
                                            ),
                                            size="2",
                                        ),
                                        padding="0.5em",
                                        border_radius="6px",
                                        background=rx.cond(
                                            State.pdf_batch_selected_pdfs.contains(pdf),
                                            "var(--purple-a3)",
                                            "transparent",
                                        ),
                                        width="100%",
                                    ),
                                ),
                                spacing="2",
                                width="100%",
                                max_height="200px",
                                overflow_y="auto",
                            ),
                            rx.hstack(
                                rx.icon("info", size=18, color="gray"),
                                rx.text(
                                    "No PDFs available. Upload PDFs using the 'Store PDF' button above.",
                                    size="2",
                                    color="gray",
                                ),
                                spacing="2",
                                align="center",
                            ),
                        ),
                        spacing="3",
                        width="100%",
                        height="100%",
                    ),
                    variant="surface",
                    size="1",
                    height="100%",
                    flex="1",
                ),
                # Section 2: Schema Builder
                rx.card(
                    rx.vstack(
                        rx.hstack(
                            rx.icon("table-2", size=18, color="blue"),
                            rx.text("Define Table Schema", size="3", weight="bold"),
                            rx.spacer(),
                            rx.button(
                                rx.icon("plus", size=16),
                                "Add Column",
                                on_click=State.add_pdf_batch_column,
                                size="2",
                                color_scheme="blue",
                                variant="soft",
                            ),
                            spacing="2",
                            align="center",
                            width="100%",
                        ),
                        rx.cond(
                            State.pdf_batch_columns.length() > 0,
                            rx.vstack(
                                rx.foreach(
                                    State.pdf_batch_columns,
                                    lambda col, idx: rx.hstack(
                                        rx.input(
                                            placeholder="Column name",
                                            value=col["name"],
                                            on_change=lambda v: State.update_pdf_batch_column(
                                                idx, "name", v
                                            ),
                                            size="2",
                                            width="50%",
                                        ),
                                        rx.select(
                                            State.available_duck_types,
                                            value=col["type"],
                                            on_change=lambda v: State.update_pdf_batch_column(
                                                idx, "type", v
                                            ),
                                            size="2",
                                            width="40%",
                                        ),
                                        rx.icon_button(
                                            rx.icon("trash-2", size=16),
                                            on_click=lambda: State.remove_pdf_batch_column(
                                                idx
                                            ),
                                            size="2",
                                            color_scheme="red",
                                            variant="soft",
                                        ),
                                        spacing="2",
                                        align="center",
                                        width="100%",
                                    ),
                                ),
                                spacing="2",
                                width="100%",
                                max_height="250px",
                                overflow_y="auto",
                            ),
                            rx.hstack(
                                rx.icon("info", size=18, color="gray"),
                                rx.text(
                                    "Click 'Add Column' to define your table schema.",
                                    size="2",
                                    color="gray",
                                ),
                                spacing="2",
                                align="center",
                            ),
                        ),
                        spacing="3",
                        width="100%",
                        height="100%",
                    ),
                    variant="surface",
                    size="1",
                    height="100%",
                    flex="1",
                ),
                # Section 3: Configuration Options
                rx.card(
                    rx.vstack(
                        rx.hstack(
                            rx.icon("settings", size=18, color="teal"),
                            rx.text("Configuration", size="3", weight="bold"),
                            spacing="2",
                            align="center",
                        ),
                        rx.vstack(
                            # Table name input
                            rx.vstack(
                                rx.hstack(
                                    rx.text("Table Name", size="2", weight="medium"),
                                    rx.badge(
                                        "Required",
                                        color_scheme="red",
                                        variant="soft",
                                        size="1",
                                    ),
                                    spacing="2",
                                    align="center",
                                ),
                                rx.input(
                                    placeholder="Enter table name (e.g., equipment_data)",
                                    value=State.pdf_batch_table_name,
                                    on_change=State.set_pdf_batch_table_name,
                                    size="2",
                                    width="100%",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            # Optional prompt
                            rx.vstack(
                                rx.text(
                                    "Extraction Prompt (Optional)",
                                    size="2",
                                    weight="medium",
                                ),
                                rx.text_area(
                                    placeholder="Enter custom instructions for the LLM (e.g., 'Focus on technical specifications')",
                                    value=State.pdf_batch_prompt,
                                    on_change=State.set_pdf_batch_prompt,
                                    size="2",
                                    width="100%",
                                    rows="3",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            # Checkboxes
                            rx.hstack(
                                rx.checkbox(
                                    "Force Recreate Table",
                                    checked=State.pdf_batch_force_recreate,
                                    on_change=State.set_pdf_batch_force_recreate,
                                    size="2",
                                ),
                                rx.checkbox(
                                    "Include Source Column",
                                    checked=State.pdf_batch_include_source,
                                    on_change=State.set_pdf_batch_include_source,
                                    size="2",
                                ),
                                spacing="4",
                                wrap="wrap",
                            ),
                            spacing="3",
                            width="100%",
                        ),
                        spacing="3",
                        width="100%",
                        height="100%",
                    ),
                    variant="surface",
                    size="1",
                    height="100%",
                    flex="1",
                ),
                spacing="4",
                align="start",
                height="500px",
                width="100%",
            ),
            # Validation hints
            rx.cond(
                ~State.batch_can_run,
                rx.callout(
                    rx.vstack(
                        rx.text(
                            "Please complete the following:", weight="bold", size="2"
                        ),
                        rx.vstack(
                            rx.cond(
                                State.pdf_batch_table_name == "",
                                rx.text("• Enter a table name", size="2"),
                            ),
                            rx.cond(
                                State.pdf_batch_columns.length() == 0,
                                rx.text(
                                    "• Add at least one column to the schema", size="2"
                                ),
                            ),
                            rx.cond(
                                State.pdf_batch_selected_pdfs.length() == 0,
                                rx.text("• Select at least one PDF", size="2"),
                            ),
                            spacing="1",
                            align="start",
                        ),
                        spacing="2",
                        align="start",
                    ),
                    icon="alert_circle",
                    color_scheme="amber",
                    size="2",
                ),
            ),
            spacing="4",
            width="100%",
        ),
        variant="classic",
        width="100%",
    )

    # Tabs switch between EDITOR & GUI
    tabs_main_view = rx.tabs.root(
        rx.tabs.list(
            rx.tabs.trigger("SQL Editor", value="EDITOR"),
            rx.tabs.trigger("Batch Task Manager", value="GUI"),
        ),
        rx.tabs.content(
            editor_section,
            value="EDITOR",
        ),
        rx.tabs.content(
            gui_section,
            value="GUI",
        ),
        default_value="EDITOR",
        width="100%",
    )

    # Success message display
    success_display = rx.cond(
        State.success_message != "",
        rx.callout(
            State.success_message,
            icon="check",
            color_scheme="green",
            role="status",
            size="2",
        ),
    )

    # Error message display (only shows when there's an error)
    error_display = rx.cond(
        State.error_message != "",
        rx.callout(
            State.error_message,
            icon="triangle_alert",
            color_scheme="red",
            role="alert",
            size="2",
        ),
    )

    # Data table - connected to State.query_results and State.table_columns
    results_section = rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("table", size=20, color="purple"),
                rx.text(
                    "Query Results",
                    size="4",
                    weight="bold",
                ),
                rx.spacer(),
                rx.cond(
                    State.result_count != "",
                    rx.badge(
                        State.result_count,
                        color_scheme="purple",
                        variant="soft",
                        size="2",
                    ),
                    rx.text(""),
                ),
                rx.button(
                    rx.icon("download", size=18),
                    "Export Results",
                    on_click=State.export_results,
                    size="3",
                    color_scheme="purple",
                    variant="soft",
                    cursor="pointer",
                ),
                spacing="2",
                align="center",
                width="100%",
            ),
            rx.data_table(
                data=State.query_results_df,
                pagination=True,
                search=False,
                sort=True,
                style={"height": "600px", "width": "100%"},
            ),
            spacing="3",
        ),
        variant="classic",
        size="3",
    )

    # Header with title and import button
    header = rx.box(
        upload_dialog,
        rx.hstack(
            rx.hstack(
                rx.icon("database", size=32, color="teal"),
                rx.vstack(
                    rx.heading(
                        "SQL Query Tool for CSV Files",
                        size="7",
                        weight="bold",
                        color="teal",
                    ),
                    rx.text(
                        "Upload CSV files and query them using SQL powered by DuckDB",
                        size="3",
                        color="gray",
                    ),
                    align="start",
                    spacing="1",
                ),
                spacing="3",
                align="center",
            ),
            rx.spacer(),
            rx.hstack(
                rx.button(
                    rx.icon("upload", size=18),
                    "Import CSV",
                    color_scheme="teal",
                    size="3",
                    variant="solid",
                    cursor="pointer",
                    on_click=State.open_upload_dialog_csv,
                ),
                rx.button(
                    rx.icon("file-plus", size=18),
                    "Store PDF",
                    color_scheme="purple",
                    size="3",
                    variant="soft",
                    cursor="pointer",
                    on_click=State.open_upload_dialog_pdf,
                ),
                spacing="2",
            ),
            width="100%",
            align="center",
        ),
        padding="2em",
        background="linear-gradient(135deg, var(--teal-a2) 0%, var(--indigo-a2) 100%)",
        border_radius="16px",
        margin_bottom="1em",
        width="100%",
    )

    # The container with all components
    return rx.box(
        rx.vstack(
            header,
            rx.hstack(
                tables_display,
                pdf_display,
                spacing="6",
                align="start",
                width="100%",
            ),
            tabs_main_view,
            success_display,
            error_display,
            results_section,
            spacing="5",
            width="100%",
        ),
        padding="2em",
        max_width="1400px",
        margin="0 auto",
        width="100%",
    )


app = rx.App()
app.add_page(index)
