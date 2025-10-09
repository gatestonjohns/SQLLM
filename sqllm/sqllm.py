import reflex as rx
from reflex_monaco import monaco
import duckdb
import os
import pandas as pd
from typing import List
from .config import DEFAULT_SQL_QUERY
import logging
from .UDF.register import register_all_udfs
from .LLM.OpenAI import OpenAIProvider

# Initialize database connection at module level
_db_connection = duckdb.connect(database=":memory:")

# Init other necessary clients/connections
_llm_provider = OpenAIProvider()

# Register all UDFs with DuckDB on module load using external UDFs registry
register_all_udfs(_db_connection, llm_provider=_llm_provider)


class State(rx.State):
    """State management for the SQL editor."""

    sql_query: str = DEFAULT_SQL_QUERY
    query_results_df: pd.DataFrame = pd.DataFrame()
    error_message: str = ""
    success_message: str = ""
    available_tables: List[str] = []
    upload_dialog_open: bool = False

    @rx.var
    def result_count(self) -> str:
        """Get the count of rows and columns in the results."""
        if self.query_results_df.empty:
            return ""
        return f"{len(self.query_results_df)} rows × {len(self.query_results_df.columns)} columns"

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
    def open_upload_dialog(self):
        """Open the upload dialog."""
        self.upload_dialog_open = True

    @rx.event
    def close_upload_dialog(self):
        """Close the upload dialog."""
        self.upload_dialog_open = False

    @rx.event
    def set_upload_dialog_open(self, value: bool):
        """Set the upload dialog open state."""
        self.upload_dialog_open = value

    @rx.event
    def execute_query(self):
        """Execute the SQL query and update results."""
        try:
            self._reset_before_query_execution()

            self.query_results_df = _db_connection.execute(self.sql_query).fetchdf()

            logging.info(
                f"Query executed successfully: {len(self.query_results_df)} rows returned"
            )

        except Exception as e:
            self.error_message = f"Error: {str(e)}"
            logging.error(f"✗ Query error: {e}")

    @rx.event
    async def handle_upload(self, files: List[rx.UploadFile]):
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

                # Extract table name from filename (without .csv extension)
                table_name = os.path.splitext(file.filename)[0]

                # Load into DuckDB
                _db_connection.execute(
                    f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_csv_auto('{file_path}')"
                )

                # Update available tables list
                if table_name not in self.available_tables:
                    self.available_tables.append(table_name)

                self.success_message = (
                    f"Successfully loaded {file.filename} as table '{table_name}'"
                )
                logging.info(
                    f"Loaded {file.filename} into DuckDB as table '{table_name}'"
                )

            except Exception as e:
                self.error_message = f"Error uploading {file.filename}: {str(e)}"
                logging.error(f"✗ Error uploading {file.filename}: {e}")
                return

        # Close the dialog after all uploads complete successfully
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


def index():
    # File upload modal dialog
    upload_dialog = rx.dialog.root(
        rx.dialog.trigger(
            rx.button(
                rx.icon("upload", size=18),
                "Import CSV",
                color_scheme="teal",
                size="3",
                variant="solid",
                cursor="pointer",
            ),
        ),
        rx.dialog.content(
            rx.vstack(
                rx.dialog.title(
                    rx.hstack(
                        rx.icon("database", size=24, color="teal"),
                        "Import CSV Files",
                        spacing="2",
                        align="center",
                    ),
                ),
                rx.dialog.description(
                    "Upload CSV files to query them with SQL. Each file will be loaded as a separate table.",
                    size="2",
                    color="gray",
                ),
                rx.vstack(
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
                        accept={
                            "text/csv": [".csv"],
                        },
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
                        "Upload Files",
                        on_click=State.handle_upload(
                            rx.upload_files(upload_id="csv_upload")
                        ),
                        size="3",
                        color_scheme="teal",
                        width="100%",
                        cursor="pointer",
                    ),
                    spacing="4",
                    width="100%",
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
        on_open_change=State.set_upload_dialog_open,
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
                        lambda table: rx.badge(
                            rx.icon("table-2", size=14),
                            table,
                            color_scheme="blue",
                            variant="soft",
                            size="2",
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
            upload_dialog,
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
            tables_display,
            editor_section,
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
