import reflex as rx
import os
import logging
from ..state import State


class BatchState(rx.State):
    """State management for batch PDF processing."""

    pdf_batch_selected_pdfs: list[str] = []
    pdf_batch_columns: list[dict[str, str]] = []
    pdf_batch_table_name: str = ""
    pdf_batch_prompt: str = ""
    pdf_batch_force_recreate: bool = False
    pdf_batch_include_source: bool = False

    @rx.var
    def available_duck_types(self) -> list[str]:
        """Get available DuckDB types for schema builder."""
        return [
            "VARCHAR",
            "INTEGER",
            "BIGINT",
            "DOUBLE",
            "BOOLEAN",
            "DATE",
            "TIMESTAMP",
        ]

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
            # Get the main state to access shared functionality
            main_state = await self.get_state(State)

            # Validate inputs
            table_name = self.pdf_batch_table_name.strip()
            if not table_name:
                main_state.error_message = "Table name is required"
                return

            if not self.pdf_batch_columns:
                main_state.error_message = "At least one column must be defined"
                return

            if not self.pdf_batch_selected_pdfs:
                main_state.error_message = "At least one PDF must be selected"
                return

            # Build schema string
            schema_parts = []
            for col in self.pdf_batch_columns:
                col_name = col.get("name", "").strip()
                col_type = col.get("type", "TEXT").strip().upper()

                if not col_name:
                    main_state.error_message = "All columns must have a name"
                    return

                schema_parts.append(f"{col_name} {col_type}")

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
            create_table_sql = f"{create_clause} {table_name} AS {union_query};"
            return_new_table_sql = f"SELECT * FROM {table_name};"
            full_sql = f"{create_table_sql}\n{return_new_table_sql}"
            print("full_sql from gui:", full_sql)
            
            return main_state.execute_query(full_sql)

        except Exception as e:
            main_state = await self.get_state(State)
            main_state.is_loading = False
            main_state.error_message = f"Error during batch ingestion: {str(e)}"
            logging.error(f"✗ Batch ingestion error: {e}")

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
        """Set the force recreate flag for batch processing."""
        self.pdf_batch_force_recreate = value

    @rx.event
    def set_pdf_batch_include_source(self, value: bool):
        """Set the include source flag for batch processing."""
        self.pdf_batch_include_source = value


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
                            rx.vstack(
                                rx.foreach(
                                    BatchState.pdf_batch_columns,
                                    lambda col, idx: rx.hstack(
                                        rx.input(
                                            placeholder="Column name",
                                            value=col["name"],
                                            on_change=lambda v: BatchState.update_pdf_batch_column(
                                                idx, "name", v
                                            ),
                                            size="2",
                                            width="50%",
                                        ),
                                        rx.select(
                                            BatchState.available_duck_types,
                                            value=col["type"],
                                            on_change=lambda v: BatchState.update_pdf_batch_column(
                                                idx, "type", v
                                            ),
                                            size="2",
                                            width="40%",
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
                                    "Force Recreate Table",
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
                            # Optional prompt
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
                                    rows="15",
                                ),
                                spacing="1",
                                width="100%",
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
