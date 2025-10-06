import reflex as rx
from reflex_monaco import monaco
import duckdb
import os
import pandas as pd
from typing import List

# Initialize database connection at module level
_db_connection = duckdb.connect(database=':memory:')

class State(rx.State):
    """State management for the SQL editor."""

    sql_query: str = "-- Upload a CSV file to get started\n-- Example: SELECT * FROM your_table LIMIT 10"
    query_results_df: pd.DataFrame = pd.DataFrame()
    error_message: str = ""
    success_message: str = ""
    available_tables: List[str] = []

    @rx.event
    def set_sql_query(self, sql_query: str):
        """Set the SQL query."""
        self.sql_query = sql_query

    @rx.event
    def execute_query(self):
        """Execute the SQL query and update results."""
        try:
            self.error_message = ""
            self.success_message = ""

            self.query_results_df = _db_connection.execute(self.sql_query).fetchdf()

            print(f"✓ Query executed successfully: {len(self.query_results_df)} rows returned")

        except Exception as e:
            self.error_message = f"Error: {str(e)}"
            self.query_results_df = pd.DataFrame()
            print(f"✗ Query error: {e}")

    async def handle_upload(self, files: List[rx.UploadFile]):
        """Handle CSV file upload and load into DuckDB."""
        for file in files:
            try:
                self.error_message = ""
                self.success_message = ""
                
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
                
                self.success_message = f"✓ Successfully loaded {file.filename} as table '{table_name}'"
                print(f"✓ Loaded {file.filename} into DuckDB as table '{table_name}'")
                
            except Exception as e:
                self.error_message = f"Error uploading {file.filename}: {str(e)}"
                print(f"✗ Error uploading {file.filename}: {e}")

    def export_results(self):
        """Export query results as CSV file."""
        try:
            if self.query_results_df.empty:
                self.error_message = "No results to export. Run a query first."
                return
            
            # Convert DataFrame to CSV string
            csv_data = self.query_results_df.to_csv(index=False)
            
            self.success_message = f"✓ Results exported successfully ({len(self.query_results_df)} rows)"
            print(f"✓ Exported {len(self.query_results_df)} rows")
            
            # Trigger download by passing data directly
            return rx.download(
                data=csv_data,
                filename="query_results.csv"
            )
            
        except Exception as e:
            self.error_message = f"Error exporting results: {str(e)}"
            print(f"✗ Error exporting: {e}")

def index():
    # File upload modal dialog
    upload_dialog = rx.dialog.root(
        rx.dialog.trigger(
            rx.button(
                rx.icon("upload"),
                "Import CSV",
                color_scheme="green",
                size="3",
            ),
        ),
        rx.dialog.content(
            rx.dialog.title("Import CSV Files"),
            rx.dialog.description(
                "Upload CSV files to query them with SQL. Each file will be loaded as a separate table.",
            ),
            rx.vstack(
                rx.upload(
                    rx.vstack(
                        rx.button(
                            "Select CSV Files",
                            color_scheme="green",
                            size="2",
                        ),
                        rx.text(
                            "Drag and drop CSV files here or click to browse",
                            size="2",
                            color="gray",
                        ),
                    ),
                    id="csv_upload",
                    multiple=True,
                    accept={
                        "text/csv": [".csv"],
                    },
                    max_files=5,
                    border="1px dashed #ccc",
                    padding="2em",
                    border_radius="8px",
                ),
                rx.hstack(
                    rx.foreach(
                        rx.selected_files("csv_upload"),
                        lambda file: rx.text(file),
                    ),
                    spacing="2",
                    wrap="wrap",
                ),
                rx.button(
                    "Upload",
                    on_click=State.handle_upload(rx.upload_files(upload_id="csv_upload")),
                    size="3",
                    color_scheme="green",
                    width="100%",
                ),
                spacing="4",
                width="100%",
            ),
            rx.flex(
                rx.dialog.close(
                    rx.button(
                        "Close",
                        color_scheme="gray",
                        variant="soft",
                    ),
                ),
                spacing="3",
                margin_top="16px",
                justify="end",
            ),
            style={"max_width": "500px"},
        ),
    )
    
    # Available tables display
    tables_display = rx.cond(
        State.available_tables.length() > 0,
        rx.hstack(
            rx.text(
                "Available tables:",
                size="2",
                weight="bold",
            ),
            rx.foreach(
                State.available_tables,
                lambda table: rx.badge(table, color_scheme="blue"),
            ),
            spacing="2",
            align="center",
            wrap="wrap",
        ),
        rx.text(
            "No tables loaded yet. Click 'Import CSV' to get started.",
            size="2",
            color="gray",
            style={"font-style": "italic"},
        ),
    )

    # Monaco SQL Editor - bound to State.sql_query
    editor = monaco(
        default_language='sql',
        value=State.sql_query,
        on_change=State.set_sql_query,
        height="400px",
        width="100%"
    )

    # Query action buttons
    action_buttons = rx.hstack(
        rx.button(
            "Run Query",
            on_click=State.execute_query,
            size="3",
            color_scheme="blue",
        ),
        rx.button(
            "Export Results",
            on_click=State.export_results,
            size="3",
            color_scheme="purple",
        ),
        spacing="3",
    )

    # Success message display
    success_display = rx.cond(
        State.success_message != "",
        rx.callout(
            State.success_message,
            color_scheme="green",
            role="status",
        ),
    )

    # Error message display (only shows when there's an error)
    error_display = rx.cond(
        State.error_message != "",
        rx.callout(
            State.error_message,
            color_scheme="red",
            role="alert",
        ),
    )

    # Data table - connected to State.query_results and State.table_columns
    table = rx.data_table(
        data=State.query_results_df,
        pagination=True,
        search=True,
        sort=True,
        style={"height": "600px", "width": "100%"}
    )
    
    # Header with title and import button
    header = rx.hstack(
        rx.vstack(
            rx.heading("SQL Query Tool for CSV Files", size="6"),
            rx.text(
                "Upload CSV files and query them using SQL powered by DuckDB",
                size="3",
                color="gray",
            ),
            align="start",
            spacing="1",
        ),
        rx.spacer(),
        upload_dialog,
        width="100%",
        align="center",
    )
    
    # The container with all components
    return rx.vstack(
        header,
        rx.divider(),
        tables_display,
        rx.divider(),
        rx.heading("SQL Query Editor", size="4"),
        editor,
        action_buttons,
        success_display,
        error_display,
        table,
        spacing="4",
        width="100%",
        padding="2em",
    )

app = rx.App()
app.add_page(index)
