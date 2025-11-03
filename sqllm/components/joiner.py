import reflex as rx
import logging

from sqlglot.expressions import From
from ..state import State
from ..backend.Engine.engine import TableRepresentationObject


class JoinerState(rx.State):
    """State management for the joiner GUI section."""

    joiner_dialog_open: bool = False
    new_table_name: str = ""
    left_table_name: str = ""
    right_table_name: str = ""
    left_table: TableRepresentationObject | None = None
    right_table: TableRepresentationObject | None = None

    # Join criteria (list of dicts with left_col, right_col, mechanism, weight)
    join_criteria: list[dict[str, str]] = []

    # Join configuration
    k_value: int = 5  # Number of top candidates
    join_prompt: str = ""

    # Available matching mechanisms
    available_mechanisms: list[str] = [
        "semantic_distance",
        "fuzzy_match",
        "exact_match",
        "numeric_distance",
        "arithmetic_asc",
        "arithmetic_desc",
    ]

    async def _get_table_by_name(self, name: str) -> TableRepresentationObject | None:
        """Get the table by name."""
        state = await self.get_state(State)
        table = next(
            (table for table in state.available_tables if table.name == name), None
        )
        if table is None:
            raise ValueError(f"Table {name} not found")
        return table

    @rx.var
    async def available_table_names(self) -> list[str]:
        """Get the available tables."""
        state = await self.get_state(State)
        return [table.name for table in state.available_tables]

    @rx.event
    def set_new_table_name(self, value: str):
        """Set the new table name."""
        self.new_table_name = value

    @rx.event
    async def set_left_table_name(self, value: str):
        """Set the left table name."""
        self.left_table_name = value
        await self.set_left_table(value)

    @rx.event
    async def set_right_table_name(self, value: str):
        """Set the right table name."""
        self.right_table_name = value
        await self.set_right_table(value)

    @rx.event
    async def set_left_table(self, value: str):
        """Set the left table."""
        self.left_table = await self._get_table_by_name(value)

    @rx.event
    async def set_right_table(self, value: str):
        """Set the right table."""
        self.right_table = await self._get_table_by_name(value)

    @rx.var
    def left_column_names(self) -> list[str]:
        """Get column names from left table."""
        if self.left_table is None:
            return []
        return [col.name for col in self.left_table.columns]

    @rx.var
    def right_column_names(self) -> list[str]:
        """Get column names from right table."""
        if self.right_table is None:
            return []
        return [col.name for col in self.right_table.columns]

    @rx.var
    def has_valid_criteria(self) -> bool:
        """Check if all criteria have valid type matches."""
        if not self.join_criteria:
            return False

        for criterion in self.join_criteria:
            left_col = criterion.get("left_col", "")
            right_col = criterion.get("right_col", "")

            # Skip incomplete criteria
            if not left_col or not right_col:
                return False

            is_valid, _ = self._validate_criterion(criterion)
            if not is_valid:
                return False

        return True

    @rx.var
    def can_execute_join(self) -> bool:
        """Check if join can be executed."""
        return (
            self.new_table_name.strip() != ""  # TODO: sql sanitize new table name
            and self.left_table is not None
            and self.right_table is not None
            and self.left_table_name != self.right_table_name
            and len(self.join_criteria) > 0
            and self.has_valid_criteria
            and bool(self.join_prompt.strip())
        )

    @rx.event
    def add_join_criterion(self):
        """Add a new join criterion."""
        self.join_criteria.append(
            {
                "left_col": "",
                "right_col": "",
                "mechanism": "semantic_distance",
                "weight": "1.0",
            }
        )

    @rx.event
    def remove_join_criterion(self, index: int):
        """Remove a join criterion."""
        if 0 <= index < len(self.join_criteria):
            self.join_criteria.pop(index)

    @rx.event
    def update_join_criterion(self, index: int, field: str, value: str):
        """Update a field in a join criterion."""
        if 0 <= index < len(self.join_criteria):
            self.join_criteria[index][field] = value

    @rx.event
    def set_k_value(self, value: str):
        """Set the k value."""
        try:
            self.k_value = max(1, int(value))
        except (ValueError, TypeError):
            self.k_value = 5

    @rx.event
    def set_join_prompt(self, value: str):
        """Set the join prompt."""
        self.join_prompt = value

    @rx.event
    async def reset_all_inputs(self):
        """Reset all input elements to their default/empty values."""
        self.new_table_name = ""
        self.left_table_name = ""
        self.right_table_name = ""
        self.left_table = None
        self.right_table = None
        self.join_criteria = []
        self.k_value = 5
        self.join_prompt = ""

        state = await self.get_state(State)
        state._reset_before_query_execution()

    def _get_column_type(self, table: TableRepresentationObject, col_name: str) -> str:
        """Get the type of a column in a table."""
        for col in table.columns:
            if col.name == col_name:
                return col.type.upper()
        return ""

    def _is_numeric_type(self, col_type: str) -> bool:
        """Check if a column type is numeric."""
        numeric_types = ["INTEGER", "BIGINT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC"]
        return any(nt in col_type.upper() for nt in numeric_types)

    def _is_text_type(self, col_type: str) -> bool:
        """Check if a column type is text."""
        text_types = ["TEXT", "VARCHAR", "CHAR", "STRING"]
        return any(tt in col_type.upper() for tt in text_types)

    def _validate_criterion(self, criterion: dict) -> tuple[bool, str]:
        """Validate a single criterion. Returns (is_valid, error_message)."""
        left_col = criterion.get("left_col", "")
        right_col = criterion.get("right_col", "")
        mechanism = criterion.get("mechanism", "")

        if not left_col or not right_col:
            return False, "Both columns must be selected"

        # Get column types
        left_type = self._get_column_type(self.left_table, left_col)
        right_type = self._get_column_type(self.right_table, right_col)

        if not left_type or not right_type:
            return False, "Column not found in table"

        # Check type compatibility
        left_numeric = self._is_numeric_type(left_type)
        right_numeric = self._is_numeric_type(right_type)
        left_text = self._is_text_type(left_type)
        right_text = self._is_text_type(right_type)

        # Both should be same category (numeric or text)
        if left_numeric != right_numeric:
            return (
                False,
                f"Type mismatch: {left_col} ({left_type}) vs {right_col} ({right_type})",
            )

        # Check mechanism compatibility
        if mechanism in ["semantic_distance", "fuzzy_match", "exact_match"]:
            if not (left_text and right_text):
                return False, f"{mechanism} requires text columns"

        if mechanism in ["numeric_distance", "arithmetic_asc", "arithmetic_desc"]:
            if not (left_numeric and right_numeric):
                return False, f"{mechanism} requires numeric columns"

        return True, ""

    @rx.var
    def criterion_validation_errors(self) -> list[str]:
        """Get validation error messages for all criteria."""
        errors = []
        for criterion in self.join_criteria:
            left_col = criterion.get("left_col", "")
            right_col = criterion.get("right_col", "")

            # Don't show errors for incomplete criteria
            if not left_col or not right_col:
                errors.append("")
                continue

            is_valid, error_msg = self._validate_criterion(criterion)
            errors.append("" if is_valid else error_msg)

        return errors

    @rx.event
    async def validate_and_execute_join(self):
        """Validate inputs and execute the join."""
        try:
            # Get main state
            main_state = await self.get_state(State)

            # Validate tables
            if self.left_table is None or self.right_table is None:
                main_state.error_message = "Both left and right tables must be selected"
                main_state.is_loading = False
                return

            # Validate tables are different
            if self.left_table_name == self.right_table_name:
                main_state.error_message = "Left and right tables must be different. Please select two different tables to join."
                main_state.is_loading = False
                return

            # Validate criteria
            if not self.join_criteria:
                main_state.error_message = "At least one join criterion must be defined"
                main_state.is_loading = False
                return

            # Validate prompt
            if not self.join_prompt.strip():
                main_state.error_message = "Join prompt is required"
                main_state.is_loading = False
                return

            # Validate each criterion
            for idx, criterion in enumerate(self.join_criteria):
                is_valid, error_msg = self._validate_criterion(criterion)
                if not is_valid:
                    main_state.error_message = f"Criterion {idx + 1}: {error_msg}"
                    main_state.is_loading = False
                    return

            # Generate SQL
            sql = self._generate_join_sql()

            # Pretty print SQL for debugging
            try:
                import sqlglot

                formatted_sql = sqlglot.parse_one(sql).sql(
                    dialect="duckdb", pretty=True
                )
                print("\n" + "=" * 80)
                print("GENERATED LLM JOIN SQL:")
                print("=" * 80)
                print(formatted_sql)
                print("=" * 80 + "\n")
            except Exception as e:
                print("\n" + "=" * 80)
                print("GENERATED LLM JOIN SQL (unformatted):")
                print("=" * 80)
                print(sql)
                print("=" * 80 + "\n")
                logging.warning(f"Could not format SQL for debug output: {e}")

            # Execute the query
            logging.info(
                f"Executing LLM join: {self.left_table_name} ⋈ {self.right_table_name}"
            )
            return State.execute_query(sql)

        except Exception as e:
            raise RuntimeError(f"Error executing join: {str(e)}")

    def _generate_join_sql(self) -> str:
        """Generate the SQL for the join with column renaming."""
        # Build rename mappings
        left_renames = {}
        right_renames = {}
        algorithm_cols = []

        for idx, criterion in enumerate(self.join_criteria):
            left_col = criterion["left_col"]
            right_col = criterion["right_col"]
            mechanism = criterion["mechanism"]
            weight = criterion.get("weight", "1.0")

            # Use left column name as the unified name (better context for LLM)
            unified_name = left_col
            left_renames[left_col] = unified_name
            right_renames[right_col] = unified_name

            # Add to algorithm string
            algorithm_cols.append(f"{unified_name} {mechanism} {weight}")

        # Build algorithm string
        algorithm_str = f"{self.k_value}: " + ", ".join(algorithm_cols)

        # Build SELECT statements for renaming (as nested queries)
        left_select_parts = []
        for orig_col, new_col in left_renames.items():
            left_select_parts.append(f"{orig_col} AS {new_col}")

        # Use EXCLUDE to avoid selecting renamed columns twice
        if left_renames:
            excluded_cols = ", ".join(left_renames.keys())
            left_select_parts.append(f"* EXCLUDE ({excluded_cols})")
        else:
            left_select_parts.append("*")

        left_select = ", ".join(left_select_parts)
        left_query = f"(SELECT {left_select} FROM {self.left_table_name})"

        right_select_parts = []
        for orig_col, new_col in right_renames.items():
            right_select_parts.append(f"{orig_col} AS {new_col}")

        # Use EXCLUDE to avoid selecting renamed columns twice
        if right_renames:
            excluded_cols = ", ".join(right_renames.keys())
            right_select_parts.append(f"* EXCLUDE ({excluded_cols})")
        else:
            right_select_parts.append("*")

        right_select = ", ".join(right_select_parts)
        right_query = f"(SELECT {right_select} FROM {self.right_table_name})"

        # Escape prompt
        escaped_prompt = self.join_prompt.replace("'", "''")

        # Build final SQL with nested SELECT statements as arguments
        sql = f"""SELECT * FROM llm_join(
    '{self.new_table_name}',
    '{left_query}',
    '{right_query}',
    '{algorithm_str}',
    '{escaped_prompt}'
)"""

        return sql


def table_representation(table: TableRepresentationObject) -> rx.Component:
    """Display table metadata using a prettier card-based layout."""
    if table is None:
        return rx.box(
            rx.hstack(
                rx.icon("info", size=16, color="gray"),
                rx.text(
                    "No table selected",
                    size="2",
                    color="gray",
                    style={"fontStyle": "italic"},
                ),
                spacing="2",
                align="center",
            ),
            padding="1em",
            border_radius="6px",
            background="var(--gray-a2)",
        )

    return rx.vstack(
        # Table info badge
        rx.hstack(
            rx.badge(
                rx.hstack(
                    rx.icon("table-2", size=14),
                    rx.text(table.name, size="2"),
                    spacing="1",
                    align="center",
                ),
                color_scheme="blue",
                variant="soft",
                size="2",
            ),
            rx.badge(
                f"{table.row_count} rows",
                color_scheme="gray",
                variant="soft",
                size="1",
            ),
            spacing="2",
            align="center",
        ),
        # Columns section
        rx.vstack(
            rx.text(
                "Available Columns:",
                size="3",
                weight="medium",
                color="gray",
            ),
            rx.vstack(
                rx.foreach(
                    table.columns,
                    lambda col: rx.hstack(
                        rx.icon("circle", size=10, color="blue"),
                        rx.text(col.name, size="3", weight="medium"),
                        rx.spacer(),
                        rx.badge(col.type, size="2", variant="surface"),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                ),
                spacing="2",
                width="100%",
            ),
            spacing="3",
            width="100%",
        ),
        spacing="3",
        width="100%",
        padding="0.5em",
        border_radius="6px",
        background="var(--gray-a2)",
    )


def joiner_section() -> rx.Component:
    return rx.card(
        rx.vstack(
            # Header with Execute Button
            rx.hstack(
                rx.hstack(
                    rx.icon("merge", size=20, color="orange"),
                    rx.text(
                        "Smart Join (LLM-Powered)",
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
                        on_click=JoinerState.reset_all_inputs,
                        size="1",
                        color_scheme="gray",
                        variant="outline",
                        cursor="pointer",
                    ),
                    rx.button(
                        rx.icon("play", size=18),
                        "Execute Join",
                        on_click=JoinerState.validate_and_execute_join,
                        size="3",
                        color_scheme="orange",
                        variant="solid",
                        disabled=~JoinerState.can_execute_join,
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
            rx.card(
                rx.vstack(
                    rx.text("New Table Name", size="2", weight="medium"),
                    rx.input(
                        type="text",
                        placeholder="new_table_name",
                        value=JoinerState.new_table_name,
                        on_change=JoinerState.set_new_table_name,
                        width="100%",
                    ),
                ),
                variant="surface",
                size="1",
                width="100%",
            ),
            # Left and Right Tables
            rx.hstack(
                rx.card(
                    rx.vstack(
                        rx.hstack(
                            rx.icon("database", size=18, color="blue"),
                            rx.text("Left Table (Source)", size="3", weight="bold"),
                            spacing="2",
                            align="center",
                        ),
                        rx.text(
                            "Select the table containing rows you want to match from",
                            size="1",
                            color="gray",
                        ),
                        rx.select(
                            JoinerState.available_table_names,
                            value=JoinerState.left_table_name,
                            placeholder="Select source table...",
                            on_change=JoinerState.set_left_table_name,
                            width="100%",
                            size="2",
                        ),
                        table_representation(JoinerState.left_table),
                        spacing="3",
                        width="100%",
                    ),
                    variant="surface",
                    size="1",
                    flex="1",
                ),
                rx.card(
                    rx.vstack(
                        rx.hstack(
                            rx.icon("database", size=18, color="green"),
                            rx.text("Right Table (Target)", size="3", weight="bold"),
                            spacing="2",
                            align="center",
                        ),
                        rx.text(
                            "Select the table to search for matching rows in",
                            size="1",
                            color="gray",
                        ),
                        rx.select(
                            JoinerState.available_table_names,
                            value=JoinerState.right_table_name,
                            placeholder="Select target table...",
                            on_change=JoinerState.set_right_table_name,
                            width="100%",
                            size="2",
                        ),
                        table_representation(JoinerState.right_table),
                        spacing="3",
                        width="100%",
                    ),
                    variant="surface",
                    size="1",
                    flex="1",
                ),
                spacing="4",
                width="100%",
                align="start",
            ),
            # Configuration Card (moved after tables)
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("settings", size=18, color="teal"),
                        rx.text("Join Configuration", size="3", weight="bold"),
                        spacing="2",
                        align="center",
                    ),
                    # K Value (full width)
                    rx.vstack(
                        rx.hstack(
                            rx.text("Top K Candidates", size="2", weight="medium"),
                            rx.badge(
                                "Required",
                                color_scheme="teal",
                                variant="soft",
                                size="1",
                            ),
                            spacing="2",
                            align="center",
                        ),
                        rx.text(
                            "Number of best matching candidates to consider before LLM makes final decision (higher = more thorough but slower)",
                            size="1",
                            color="gray",
                        ),
                        rx.input(
                            type="number",
                            placeholder="5",
                            value=JoinerState.k_value,
                            on_change=JoinerState.set_k_value,
                            size="2",
                            width="100%",
                            min="1",
                        ),
                        spacing="1",
                        width="100%",
                    ),
                    # Join Prompt (full width)
                    rx.vstack(
                        rx.hstack(
                            rx.text(
                                "Join Instructions for LLM", size="2", weight="medium"
                            ),
                            rx.badge(
                                "Required",
                                color_scheme="teal",
                                variant="soft",
                                size="1",
                            ),
                            spacing="2",
                            align="center",
                        ),
                        rx.text(
                            "Describe how to match rows. Be specific about what makes a good match (e.g., 'Match customers by name and email, accounting for nicknames and typos')",
                            size="1",
                            color="gray",
                        ),
                        rx.text_area(
                            placeholder="Example: Match customers based on name similarity and email address. Consider common name variations like 'Bob' for 'Robert'.",
                            value=JoinerState.join_prompt,
                            on_change=JoinerState.set_join_prompt,
                            size="2",
                            width="100%",
                            rows="3",
                        ),
                        spacing="1",
                        width="100%",
                    ),
                    spacing="3",
                    width="100%",
                ),
                variant="surface",
                size="1",
                width="100%",
            ),
            # Criteria Builder Card
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("combine", size=18, color="purple"),
                        rx.text("Matching Criteria", size="3", weight="bold"),
                        rx.spacer(),
                        rx.button(
                            rx.icon("plus", size=16),
                            "Add Criterion",
                            on_click=JoinerState.add_join_criterion,
                            size="2",
                            color_scheme="purple",
                            variant="soft",
                            # TODO: are these comparison methods right?
                            disabled=(JoinerState.left_table == None)
                            | (JoinerState.right_table == None),
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                    rx.text(
                        "Define which columns to compare and how to match them. The system will pre-filter candidates, then the LLM picks the best match.",
                        size="1",
                        color="gray",
                    ),
                    rx.cond(
                        JoinerState.join_criteria.length() > 0,
                        rx.vstack(
                            rx.foreach(
                                JoinerState.join_criteria,
                                lambda criterion, idx: rx.vstack(
                                    rx.hstack(
                                        # Left Column
                                        rx.vstack(
                                            rx.text(
                                                "Source Column",
                                                size="1",
                                                weight="medium",
                                                color="gray",
                                            ),
                                            rx.select(
                                                JoinerState.left_column_names,
                                                placeholder="Choose from left...",
                                                value=criterion["left_col"],
                                                on_change=lambda v: JoinerState.update_join_criterion(
                                                    idx, "left_col", v
                                                ),
                                                size="2",
                                                width="100%",
                                            ),
                                            spacing="1",
                                            flex="2",
                                            width="100%",
                                        ),
                                        # Arrow icon
                                        rx.box(
                                            rx.icon(
                                                "arrow-right-left",
                                                size=20,
                                                color="purple",
                                            ),
                                            padding_top="20px",
                                        ),
                                        # Right Column
                                        rx.vstack(
                                            rx.text(
                                                "Target Column",
                                                size="1",
                                                weight="medium",
                                                color="gray",
                                            ),
                                            rx.select(
                                                JoinerState.right_column_names,
                                                placeholder="Choose from right...",
                                                value=criterion["right_col"],
                                                on_change=lambda v: JoinerState.update_join_criterion(
                                                    idx, "right_col", v
                                                ),
                                                size="2",
                                                width="100%",
                                            ),
                                            spacing="1",
                                            flex="2",
                                            width="100%",
                                        ),
                                        # Mechanism
                                        rx.vstack(
                                            rx.text(
                                                "Similarity Method",
                                                size="1",
                                                weight="medium",
                                                color="gray",
                                            ),
                                            rx.select(
                                                JoinerState.available_mechanisms,
                                                value=criterion["mechanism"],
                                                on_change=lambda v: JoinerState.update_join_criterion(
                                                    idx, "mechanism", v
                                                ),
                                                size="2",
                                                width="100%",
                                            ),
                                            spacing="1",
                                            flex="2",
                                            width="100%",
                                        ),
                                        # Weight
                                        rx.vstack(
                                            rx.text(
                                                "Importance",
                                                size="1",
                                                weight="medium",
                                                color="gray",
                                            ),
                                            rx.input(
                                                type="number",
                                                placeholder="1.0",
                                                value=criterion["weight"],
                                                on_change=lambda v: JoinerState.update_join_criterion(
                                                    idx, "weight", v
                                                ),
                                                size="2",
                                                width="100%",
                                                step="0.1",
                                            ),
                                            spacing="1",
                                            flex="1",
                                            width="100%",
                                        ),
                                        # Delete button
                                        rx.box(
                                            rx.icon_button(
                                                rx.icon("trash-2", size=16),
                                                on_click=lambda: JoinerState.remove_join_criterion(
                                                    idx
                                                ),
                                                size="2",
                                                color_scheme="red",
                                                variant="soft",
                                            ),
                                            padding_top="20px",
                                        ),
                                        spacing="2",
                                        align="start",
                                        width="100%",
                                    ),
                                    # Validation error message
                                    rx.cond(
                                        JoinerState.criterion_validation_errors[idx]
                                        != "",
                                        rx.hstack(
                                            rx.icon(
                                                "circle_alert", size=16, color="red"
                                            ),
                                            rx.text(
                                                JoinerState.criterion_validation_errors[
                                                    idx
                                                ],
                                                size="2",
                                                color="red",
                                                weight="medium",
                                            ),
                                            spacing="2",
                                            align="center",
                                        ),
                                    ),
                                    spacing="2",
                                    width="100%",
                                    padding="0.75em",
                                    border_radius="8px",
                                    background=rx.cond(
                                        JoinerState.criterion_validation_errors[idx]
                                        != "",
                                        "var(--red-a2)",
                                        "var(--purple-a2)",
                                    ),
                                    border=rx.cond(
                                        JoinerState.criterion_validation_errors[idx]
                                        != "",
                                        "2px solid var(--red-a6)",
                                        "1px solid var(--purple-a4)",
                                    ),
                                ),
                            ),
                            spacing="2",
                            width="100%",
                            max_height="300px",
                            overflow_y="auto",
                        ),
                        rx.box(
                            rx.hstack(
                                rx.icon("info", size=18, color="gray"),
                                rx.text(
                                    "Select tables above, then click 'Add Criterion' to define column matching rules.",
                                    size="2",
                                    color="gray",
                                ),
                                spacing="2",
                                align="center",
                            ),
                            padding="1em",
                            border_radius="6px",
                            background="var(--gray-a2)",
                        ),
                    ),
                    spacing="3",
                    width="100%",
                ),
                variant="surface",
                size="1",
                width="100%",
            ),
            # Validation hints
            rx.cond(
                ~JoinerState.can_execute_join,
                rx.callout(
                    rx.vstack(
                        rx.text(
                            "Please complete the following:", weight="bold", size="2"
                        ),
                        rx.vstack(
                            rx.cond(
                                JoinerState.left_table == None,
                                rx.text("• Select a left table", size="2"),
                            ),
                            rx.cond(
                                JoinerState.right_table == None,
                                rx.text("• Select a right table", size="2"),
                            ),
                            rx.cond(
                                (JoinerState.left_table != None)
                                & (JoinerState.right_table != None)
                                & (
                                    JoinerState.left_table_name
                                    == JoinerState.right_table_name
                                ),
                                rx.text(
                                    "• Left and right tables must be different",
                                    size="2",
                                    color="red",
                                    weight="medium",
                                ),
                            ),
                            rx.cond(
                                JoinerState.join_criteria.length() == 0,
                                rx.text("• Add at least one match criterion", size="2"),
                            ),
                            rx.cond(
                                (JoinerState.join_criteria.length() > 0)
                                & ~JoinerState.has_valid_criteria,
                                rx.text(
                                    "• Fix matching criteria: each criterion must have column selected from each table and be of compatible types",
                                    size="2",
                                    color="red",
                                    weight="medium",
                                ),
                            ),
                            rx.cond(
                                JoinerState.join_prompt == "",
                                rx.text("• Enter join instructions", size="2"),
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
