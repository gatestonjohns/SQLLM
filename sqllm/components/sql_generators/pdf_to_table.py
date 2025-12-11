import reflex as rx
import os
import json
from ...state import State
from ...models.execution_task import ExecutionTask
from ...backend.Engine.schema import DataType


class BatchState(rx.State):
    """State management for batch PDF processing."""

    pdf_batch_selected_pdfs: list[str] = []
    pdf_batch_columns: list[dict[str, str]] = []
    pdf_batch_table_name: str = ""
    pdf_batch_prompt: str = ""
    pdf_batch_force_recreate: bool = False
    pdf_batch_include_source: bool = False

    @rx.var
    def available_schema_types(self) -> list[str]:
        """Get available schema types for schema builder."""
        return [data_type.value for data_type in DataType]

    @rx.var
    async def available_pdfs(self) -> list[str]:
        """Get available PDFs for batch processing."""
        return await self.get_var_value(State.available_pdfs)

    @rx.var
    def batch_can_run(self) -> bool:
        """Check if batch task can be executed."""
        return (
            bool(self.pdf_batch_table_name.strip())
            and len(self.pdf_batch_columns) > 0
            and len(self.pdf_batch_selected_pdfs) > 0
        )

    @rx.event
    def add_pdf_batch_column(self):
        """Add a new column to the batch schema."""
        self.pdf_batch_columns.append(
            {"name": "", "type": "string", "description": "", "pattern": ""}
        )

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
        table_name = self.pdf_batch_table_name.strip()

        # Build columns list for JSON schema
        columns_data = []
        for col in self.pdf_batch_columns:
            col_name = col.get("name", "").strip()
            # Basic validation
            if not col_name:
                continue

            schema_type = col.get("type", "string").strip().lower()

            col_def = {
                "name": col_name,
                "type": schema_type,
            }

            description = col.get("description", "").strip()
            if description:
                col_def["description"] = description

            pattern = col.get("pattern", "").strip()
            if pattern:
                col_def["pattern"] = pattern

            columns_data.append(col_def)

        if not columns_data:
            return  # Or show error notification

        # Serialize columns to JSON
        columns_json = json.dumps(columns_data)

        # Build new schema string format: TABLE name WITH COLUMNS [...]
        schema_str = f"TABLE {table_name} WITH COLUMNS {columns_json}"

        # Build SQL query
        create_clause = (
            "CREATE OR REPLACE TABLE"
            if self.pdf_batch_force_recreate
            else "CREATE TABLE IF NOT EXISTS"
        )

        # Build SELECT statements for each PDF
        selects = []
        for pdf_path in self.pdf_batch_selected_pdfs:
            basename = os.path.basename(pdf_path)
            # Escape single quotes for SQL string literals
            escaped_path = pdf_path.replace("'", "''")

            # Escape single quotes in schema string for SQL string literal
            escaped_schema_str = schema_str.replace("'", "''")

            # Escape prompt
            escaped_prompt = self.pdf_batch_prompt.replace("'", "''")

            # Build llm_pdf_to_table call
            if self.pdf_batch_prompt.strip():
                llm_call = f"llm_pdf_to_table('{escaped_path}', '{escaped_schema_str}', '{escaped_prompt}')"
            else:
                llm_call = f"llm_pdf_to_table('{escaped_path}', '{escaped_schema_str}')"

            # Build SELECT with optional source column
            if self.pdf_batch_include_source:
                select_stmt = f"SELECT '{basename}' AS source_pdf, * FROM {llm_call}"
            else:
                select_stmt = f"SELECT * FROM {llm_call}"

            selects.append(select_stmt)

        # Combine with UNION ALL
        union_query = " UNION ALL ".join(selects)

        # Final SQL statement
        create_table_sql = f"{create_clause} {table_name} AS {union_query};"
        return_new_table_sql = f"SELECT * FROM {table_name};"
        full_sql = f"{create_table_sql}\n{return_new_table_sql}"

        print("full_sql from gui:", full_sql)

        # Create a new execution task
        task = ExecutionTask(
            sql=full_sql,
            summary=f"CREATE `{table_name}`",
            type="PDF_TO_TABLE",
        )

        # Submit to the execution task system (following editor.py pattern)
        return State.submit_execution_task(task)

    @rx.event
    def set_pdf_batch_table_name(self, value: str):
        """Set the table name for batch processing."""
        self.pdf_batch_table_name = value

    @rx.event
    def set_pdf_batch_prompt(self, value: str):
        """Set the extraction prompt for batch processing."""
        self.pdf_batch_prompt = value

    @rx.event
    def set_pdf_batch_force_recreate(self, value: bool):
        """Set the force recreate (overwrite existing table) flag for batch processing."""
        self.pdf_batch_force_recreate = value

    @rx.event
    def set_pdf_batch_include_source(self, value: bool):
        """Set the include source flag for batch processing."""
        self.pdf_batch_include_source = value

    @rx.event
    async def toggle_all_pdfs(self):
        """Toggle all available PDFs for batch processing."""
        available = await self.get_var_value(State.available_pdfs)
        if self.pdf_batch_selected_pdfs == list(available):
            self.pdf_batch_selected_pdfs = []
        else:
            self.pdf_batch_selected_pdfs = list(available)

    @rx.event
    def reset_all_inputs(self):
        """Reset all input elements to their default/empty values."""
        self.pdf_batch_selected_pdfs = []
        self.pdf_batch_columns = []
        self.pdf_batch_table_name = ""
        self.pdf_batch_prompt = ""
        self.pdf_batch_force_recreate = False
        self.pdf_batch_include_source = False


def gui_section() -> rx.Component:
    return rx.card(
        rx.vstack(
            # Header with Run Button
            rx.hstack(
                rx.hstack(
                    rx.icon("pickaxe", size=20, color="orange"),
                    rx.text(
                        "Batch PDF to Table Converter",
                        size="4",
                        weight="bold",
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.hstack(
                    rx.button(
                        rx.icon("rotate-ccw", size=14),
                        "Reset Options",
                        on_click=BatchState.reset_all_inputs,
                        size="1",
                        color_scheme="gray",
                        variant="outline",
                        cursor="pointer",
                    ),
                    rx.button(
                        rx.icon("play", size=18),
                        "Create Table from PDFs",
                        on_click=BatchState.run_pdf_batch_ingest,
                        size="3",
                        color_scheme="purple",
                        variant="solid",
                        disabled=~BatchState.batch_can_run,
                        cursor="pointer",
                    ),
                    spacing="4",
                    align="center",
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
                            rx.button(
                                "Toggle All",
                                on_click=BatchState.toggle_all_pdfs,
                                size="2",
                                color_scheme="purple",
                                variant="soft",
                                disabled=BatchState.available_pdfs.length() == 0,
                            ),
                            rx.badge(
                                f"{BatchState.pdf_batch_selected_pdfs.length()} selected",
                                color_scheme="purple",
                                variant="soft",
                            ),
                            spacing="2",
                            align="center",
                            width="100%",
                        ),
                        rx.cond(
                            BatchState.available_pdfs.length() > 0,
                            rx.vstack(
                                rx.foreach(
                                    BatchState.available_pdfs,
                                    lambda pdf: rx.box(
                                        rx.checkbox(
                                            rx.text(pdf, size="2"),
                                            checked=BatchState.pdf_batch_selected_pdfs.contains(
                                                pdf
                                            ),
                                            on_change=lambda _: BatchState.toggle_pdf_selection(
                                                pdf
                                            ),
                                            size="2",
                                        ),
                                        padding="0.5em",
                                        border_radius="6px",
                                        background=rx.cond(
                                            BatchState.pdf_batch_selected_pdfs.contains(
                                                pdf
                                            ),
                                            "var(--purple-a3)",
                                            "transparent",
                                        ),
                                        width="100%",
                                    ),
                                ),
                                spacing="2",
                                width="100%",
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
                                on_click=BatchState.add_pdf_batch_column,
                                size="2",
                                color_scheme="blue",
                                variant="soft",
                            ),
                            spacing="2",
                            align="center",
                            width="100%",
                        ),
                        rx.cond(
                            BatchState.pdf_batch_columns.length() > 0,
                            rx.box(
                                rx.vstack(
                                    rx.foreach(
                                        BatchState.pdf_batch_columns,
                                        lambda col, idx: rx.card(
                                            rx.vstack(
                                                rx.hstack(
                                                    rx.input(
                                                        placeholder="Column Name",
                                                        value=col["name"],
                                                        on_change=lambda v: BatchState.update_pdf_batch_column(
                                                            idx, "name", v
                                                        ),
                                                        size="2",
                                                        width="70%",
                                                    ),
                                                    rx.select(
                                                        BatchState.available_schema_types,
                                                        value=col["type"],
                                                        on_change=lambda v: BatchState.update_pdf_batch_column(
                                                            idx, "type", v
                                                        ),
                                                        size="2",
                                                        width="30%",
                                                    ),
                                                    rx.icon_button(
                                                        rx.icon("trash-2", size=16),
                                                        on_click=lambda: BatchState.remove_pdf_batch_column(
                                                            idx
                                                        ),
                                                        size="2",
                                                        color_scheme="red",
                                                        variant="soft",
                                                    ),
                                                    width="100%",
                                                    spacing="2",
                                                ),
                                                rx.vstack(
                                                    rx.text_area(
                                                        placeholder="Description & Examples",
                                                        value=col["description"],
                                                        on_change=lambda v: BatchState.update_pdf_batch_column(
                                                            idx, "description", v
                                                        ),
                                                        width="100%",
                                                    ),
                                                    width="100%",
                                                    spacing="2",
                                                ),
                                                spacing="2",
                                            ),
                                            padding="3",
                                            variant="surface",
                                            width="100%",
                                        ),
                                    ),
                                    spacing="2",
                                    width="100%",
                                ),
                                overflow_y="auto",
                                height="100%",
                                width="100%",
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
                    flex="2",  # Increased flex to accommodate wider content
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
                                value=BatchState.pdf_batch_table_name,
                                on_change=BatchState.set_pdf_batch_table_name,
                                size="2",
                                width="100%",
                            ),
                            spacing="1",
                            width="100%",
                        ),
                        # Checkboxes
                        rx.hstack(
                            rx.checkbox(
                                "Overwrite Existing Table",
                                checked=BatchState.pdf_batch_force_recreate,
                                on_change=BatchState.set_pdf_batch_force_recreate,
                                size="2",
                            ),
                            rx.checkbox(
                                "Include Source Column",
                                checked=BatchState.pdf_batch_include_source,
                                on_change=BatchState.set_pdf_batch_include_source,
                                size="2",
                            ),
                            spacing="4",
                            wrap="wrap",
                        ),
                        # Optional prompt - takes remaining height
                        rx.vstack(
                            rx.text(
                                "Extraction Prompt (Optional)",
                                size="2",
                                weight="medium",
                            ),
                            rx.text_area(
                                placeholder="Enter custom instructions for the LLM (e.g., 'Focus on technical specifications')",
                                value=BatchState.pdf_batch_prompt,
                                on_change=BatchState.set_pdf_batch_prompt,
                                size="2",
                                width="100%",
                                height="100%",
                                resize="none",
                            ),
                            spacing="1",
                            width="100%",
                            flex="1",
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
                ~BatchState.batch_can_run,
                rx.callout(
                    rx.vstack(
                        rx.text(
                            "Please complete the following:", weight="bold", size="2"
                        ),
                        rx.vstack(
                            rx.cond(
                                BatchState.pdf_batch_table_name == "",
                                rx.text("• Enter a table name", size="2"),
                            ),
                            rx.cond(
                                BatchState.pdf_batch_columns.length() == 0,
                                rx.text(
                                    "• Add at least one column to the schema", size="2"
                                ),
                            ),
                            rx.cond(
                                BatchState.pdf_batch_selected_pdfs.length() == 0,
                                rx.text("• Select at least one PDF", size="2"),
                            ),
                            spacing="1",
                            align="start",
                        ),
                        spacing="2",
                        align="start",
                    ),
                    icon="circle_alert",
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
