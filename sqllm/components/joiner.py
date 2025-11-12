import reflex as rx
import logging
import json
import pandas as pd
from typing import Any

from ..state import State
from ..backend.Engine.engine import TableRepresentationObject


# Type definitions for test results
class Candidate(rx.Base):
    """A candidate match from the right table."""

    score: float
    right_row: dict[str, Any]
    breakdown: dict[str, float]


class TestResult(rx.Base):
    """Single test result row."""

    row_index: int
    left_row: dict[str, Any]
    candidates: list[Candidate]
    llm_decision: dict[str, Any] | None
    row_cost: float


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

    # Test mode state variables
    test_mode_enabled: bool = False
    test_mode_type: str = "dry"  # 'dry' or 'full'
    test_size: int = 10
    test_where_clause: str = ""
    current_test_left_sql: str = ""
    test_results: list[TestResult] = []
    test_cost_total: float = 0.0
    test_cost_total_provider: float = 0.0
    test_cost_estimate: float = 0.0
    test_cost_note: str = ""
    test_results_all_expanded: bool = True
    _test_sample_seed: int = 42  # Server-side only: seed for repeatable sampling

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
        self.current_test_left_sql = ""
        self.test_results = []
        await self.set_left_table(value)

    @rx.event
    async def set_right_table_name(self, value: str):
        """Set the right table name."""
        self.right_table_name = value
        self.test_results = []
        await self.set_right_table(value)

    @rx.event
    async def set_left_table(self, value: str):
        """Set the left table."""
        self.left_table = await self._get_table_by_name(value)
        self.current_test_left_sql = ""
        self.test_results = []

    @rx.event
    async def set_right_table(self, value: str):
        """Set the right table."""
        self.right_table = await self._get_table_by_name(value)
        self.test_results = []

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

    @rx.var
    def test_can_run(self) -> bool:
        """Check if test can be executed."""
        return (
            self.test_mode_enabled
            and self.left_table is not None
            and self.right_table is not None
            and self.left_table_name != self.right_table_name
            and len(self.join_criteria) > 0
            and self.has_valid_criteria
            and bool(self.join_prompt.strip())
            and self.test_size > 0
        )

    @rx.var
    def test_results_available(self) -> bool:
        """Check if test results are available."""
        return len(self.test_results) > 0

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
    def toggle_test_mode(self):
        """Toggle test mode on/off."""
        self.test_mode_enabled = not self.test_mode_enabled

    @rx.event
    def set_test_mode_type(self, value: str):
        """Set test mode type (dry or full)."""
        if value in ["dry", "full"]:
            self.test_mode_type = value

    @rx.event
    def set_test_size(self, value: str):
        """Set test size (1-100)."""
        try:
            size = int(value)
            self.test_size = max(1, min(100, size))
            self.current_test_left_sql = ""  # Force regeneration
        except (ValueError, TypeError):
            self.test_size = 10

    @rx.event
    def set_test_where_clause(self, value: str):
        """Set test WHERE clause."""
        self.test_where_clause = value

    @rx.event
    async def recalculate_test_rows(self):
        """Recalculate test rows based on WHERE clause."""
        import random

        self.test_results = []
        self.current_test_left_sql = ""

        # Generate new random seed for this sample
        self._test_sample_seed = random.randint(1, 999999)

        # Generate new test SQL based on WHERE clause
        if self.test_where_clause.strip():
            self.current_test_left_sql = f"SELECT * FROM {self.left_table_name} WHERE {self.test_where_clause} USING SAMPLE reservoir({self.test_size} ROWS) REPEATABLE ({self._test_sample_seed})"
        else:
            self.current_test_left_sql = f"SELECT * FROM {self.left_table_name} USING SAMPLE reservoir({self.test_size} ROWS) REPEATABLE ({self._test_sample_seed})"

    @rx.event
    async def shuffle_test_rows(self):
        """Shuffle test rows with new random selection."""
        import random

        self.test_results = []
        self.test_where_clause = ""

        # Generate new random seed for shuffled sample
        self._test_sample_seed = random.randint(1, 999999)

        self.current_test_left_sql = f"SELECT * FROM {self.left_table_name} USING SAMPLE reservoir({self.test_size} ROWS) REPEATABLE ({self._test_sample_seed})"

    @rx.event
    async def execute_test_join(self):
        """Execute test join."""
        try:
            # Get main state
            main_state = await self.get_state(State)

            # Check test mode is enabled
            if not self.test_mode_enabled:
                main_state.error_message = (
                    "Test mode must be enabled to execute test join"
                )
                main_state.is_loading = False
                return

            # Validate tables
            if self.left_table is None or self.right_table is None:
                main_state.error_message = "Both left and right tables must be selected"
                main_state.is_loading = False
                return

            # Validate tables are different
            if self.left_table_name == self.right_table_name:
                main_state.error_message = "Left and right tables must be different"
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

            # Validate test size
            if self.test_size <= 0:
                main_state.error_message = "Test size must be greater than 0"
                main_state.is_loading = False
                return

            # Validate each criterion
            for idx, criterion in enumerate(self.join_criteria):
                is_valid, error_msg = self._validate_criterion(criterion)
                if not is_valid:
                    main_state.error_message = f"Criterion {idx + 1}: {error_msg}"
                    main_state.is_loading = False
                    return

            # Generate default test SQL if not set
            if not self.current_test_left_sql:
                import random

                self._test_sample_seed = random.randint(1, 999999)
                self.current_test_left_sql = f"SELECT * FROM {self.left_table_name} USING SAMPLE reservoir({self.test_size} ROWS) REPEATABLE ({self._test_sample_seed})"

            # Generate test SQL
            sql = self._generate_test_join_sql()

            # Pretty print SQL for debugging
            try:
                import sqlglot

                formatted_sql = sqlglot.parse_one(sql).sql(
                    dialect="duckdb", pretty=True
                )
                print("\n" + "=" * 80)
                print("GENERATED TEST JOIN SQL:")
                print("=" * 80)
                print(formatted_sql)
                print("=" * 80 + "\n")
            except Exception as e:
                print("\n" + "=" * 80)
                print("GENERATED TEST JOIN SQL (unformatted):")
                print("=" * 80)
                print(sql)
                print("=" * 80 + "\n")
                logging.warning(f"Could not format SQL for debug output: {e}")

            # Execute the query
            logging.info(
                f"Executing test join: {self.left_table_name} ⋈ {self.right_table_name} (test_size={self.test_size}, mode={self.test_mode_type})"
            )
            for _ in main_state.execute_query(sql, show_results=False):
                yield

            # Get result
            result_df = main_state.query_results_df

            # Unpack JSON results
            self.test_results = self._unpack_test_results(result_df)

            # Calculate cost estimate
            await self._calculate_cost_estimate()

            logging.info(f"Test join completed with {len(self.test_results)} results")

        except Exception as e:
            raise RuntimeError(f"Error executing test join: {str(e)}")

    @rx.event
    def toggle_all_test_results(self):
        """Toggle expand/collapse state for all test results."""
        self.test_results_all_expanded = not self.test_results_all_expanded

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

        # Reset test mode variables
        self.test_mode_enabled = False
        self.test_mode_type = "dry"
        self.test_size = 10
        self.test_where_clause = ""
        self.current_test_left_sql = ""
        self.test_results = []
        self.test_cost_total = 0.0
        self.test_cost_total_provider = 0.0
        self.test_cost_estimate = 0.0
        self.test_cost_note = ""
        self._test_sample_seed = 42  # Reset to default seed

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
            return main_state.execute_query(sql)

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

    def _generate_test_join_sql(self) -> str:
        """Generate the SQL for test join."""
        # Build rename mappings (same as production join)
        left_renames = {}
        right_renames = {}
        algorithm_cols = []

        for idx, criterion in enumerate(self.join_criteria):
            left_col = criterion["left_col"]
            right_col = criterion["right_col"]
            mechanism = criterion["mechanism"]
            weight = criterion.get("weight", "1.0")

            # Use left column name as the unified name
            unified_name = left_col
            left_renames[left_col] = unified_name
            right_renames[right_col] = unified_name

            # Add to algorithm string
            algorithm_cols.append(f"{unified_name} {mechanism} {weight}")

        # Build algorithm string
        algorithm_str = f"{self.k_value}: " + ", ".join(algorithm_cols)

        # Build left query with column renaming
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

        # Use current_test_left_sql or generate default
        test_left_base = (
            self.current_test_left_sql
            if self.current_test_left_sql
            else f"SELECT * FROM {self.left_table_name} USING SAMPLE reservoir({self.test_size} ROWS) REPEATABLE ({self._test_sample_seed})"
        )
        left_query = f"(SELECT {left_select} FROM ({test_left_base}))"

        # Build right query with column renaming (same as production)
        right_select_parts = []
        for orig_col, new_col in right_renames.items():
            right_select_parts.append(f"{orig_col} AS {new_col}")

        if right_renames:
            excluded_cols = ", ".join(right_renames.keys())
            right_select_parts.append(f"* EXCLUDE ({excluded_cols})")
        else:
            right_select_parts.append("*")

        right_select = ", ".join(right_select_parts)
        right_query = f"(SELECT {right_select} FROM {self.right_table_name})"

        # Escape prompt and queries for embedding in SQL string
        escaped_prompt = self.join_prompt.replace("'", "''")
        escaped_left_query = left_query.replace("'", "''")
        escaped_right_query = right_query.replace("'", "''")

        # Build final SQL for llm_join_test
        sql = f"""SELECT * FROM llm_join_test('{escaped_left_query}', '{escaped_right_query}', '{algorithm_str}', '{escaped_prompt}', {self.test_size}, '{self.test_mode_type}')"""

        return sql

    def _unpack_test_results(self, result_df: pd.DataFrame) -> list[TestResult]:
        """Unpack JSON columns from test results."""
        results = []

        for _, row in result_df.iterrows():
            try:
                # Parse JSON columns
                left_row = json.loads(row["left_row_json"])
                candidates_raw = json.loads(row["candidates_json"])

                # Convert candidates to Candidate objects
                candidates = [
                    Candidate(
                        score=float(c["score"]),
                        right_row=c["right_row"],
                        breakdown=c["breakdown"],
                    )
                    for c in candidates_raw
                ]

                # Handle nullable llm_decision_json
                llm_decision = None
                if pd.notna(row["llm_decision_json"]):
                    llm_decision = json.loads(row["llm_decision_json"])

                # Extract row cost
                row_cost = row["row_cost"]

                # Build result object
                result = TestResult(
                    row_index=int(row["row_index"]),
                    left_row=left_row,
                    candidates=candidates,
                    llm_decision=llm_decision,
                    row_cost=float(row_cost),
                )

                results.append(result)
            except Exception as e:
                logging.error(f"Error unpacking test result row: {e}")
                continue

        return results

    async def _calculate_cost_estimate(self):
        """Calculate cost estimate for full table join."""
        # Calculate total test cost from per-row costs
        self.test_cost_total = sum(result.row_cost for result in self.test_results)

        # Get provider-reported total cost
        main_state = await self.get_state(State)
        self.test_cost_total_provider = main_state.current_query_cost

        if self.test_mode_type == "dry":
            self.test_cost_estimate = 0.0
            self.test_cost_note = (
                "Run a full test to get cost estimation for the complete join"
            )
        else:
            # Count full left table rows
            try:
                if self.test_where_clause.strip():
                    # Count with WHERE clause
                    count_sql = f"SELECT COUNT(*) FROM {self.left_table_name} WHERE {self.test_where_clause}"
                    result = main_state._engine.conn.execute(count_sql).fetchone()
                    full_left_rows = result[0]
                else:
                    # Use base table row count
                    full_left_rows = self.left_table.row_count

                # Calculate estimate using provider-reported total
                if self.test_size > 0 and self.test_cost_total_provider > 0:
                    self.test_cost_estimate = (
                        full_left_rows / self.test_size
                    ) * self.test_cost_total_provider
                    self.test_cost_note = (
                        f"Estimated cost for full join of {full_left_rows} rows"
                    )
                else:
                    self.test_cost_estimate = 0.0
                    self.test_cost_note = "Unable to estimate cost"

            except Exception as e:
                logging.error(f"Error calculating cost estimate: {e}")
                self.test_cost_estimate = 0.0
                self.test_cost_note = f"Error estimating cost: {str(e)}"


def render_candidate_card(
    candidate: Candidate, idx: int, result: TestResult
) -> rx.Component:
    """Render a single candidate card with score, data, and selection indicator."""
    # Check if this candidate is selected by LLM (LLM returns 1-indexed selection)
    is_selected = (
        result.llm_decision is not None
        and result.llm_decision.get("selected") == idx + 1
    )

    return rx.box(
        rx.vstack(
            # Header with rank, score, and selection indicator
            rx.hstack(
                rx.badge(
                    f"#{idx + 1}",
                    color_scheme="gray",
                    variant="solid",
                ),
                rx.badge(
                    f"Score: {candidate.score:.3f}",
                    color_scheme="green",
                    variant="soft",
                ),
                rx.cond(
                    is_selected,
                    rx.hstack(
                        rx.badge(
                            "LLM Choice",
                            color_scheme="orange",
                            variant="solid",
                        ),
                        rx.badge(
                            f"Confidence: {result.llm_decision['confidence']:.1%}",
                            color_scheme="orange",
                            variant="solid",
                        ),
                        spacing="2",
                        align="center",
                    ),
                    rx.fragment(),
                ),
                spacing="2",
                align="center",
            ),
            # Right row data
            rx.hstack(
                rx.foreach(
                    candidate.right_row.items(),
                    lambda item: rx.badge(
                        f"{item[0]}: {item[1]}",
                        color_scheme="green",
                        variant="outline",
                        size="1",
                    ),
                ),
                wrap="wrap",
                spacing="1",
            ),
            # Score breakdown
            rx.hstack(
                rx.text("Breakdown:", size="1", color="gray"),
                rx.foreach(
                    candidate.breakdown.items(),
                    lambda item: rx.badge(
                        f"{item[0]}: {item[1]:.2f}",
                        color_scheme="gray",
                        variant="surface",
                        size="1",
                    ),
                ),
                wrap="wrap",
                spacing="1",
            ),
            spacing="2",
            width="100%",
        ),
        padding="0.75em",
        border_radius="6px",
        border="1px solid var(--gray-a5)",
        background=rx.cond(
            is_selected,
            "var(--indigo-a3)",
            "var(--gray-a2)",
        ),
        width="100%",
    )


def test_results_panel() -> rx.Component:
    """Render the test results panel with collapsible rows."""
    return rx.card(
        rx.vstack(
            # Panel header with controls
            rx.hstack(
                rx.hstack(
                    rx.icon("flask-conical", size=18, color="indigo"),
                    rx.text("Test Results", size="3", weight="bold"),
                    spacing="2",
                    align="center",
                ),
                rx.hstack(
                    rx.badge(
                        f"{JoinerState.test_results.length()} rows tested",
                        color_scheme="indigo",
                        variant="soft",
                        size="2",
                    ),
                    rx.button(
                        rx.cond(
                            JoinerState.test_results_all_expanded,
                            "Collapse All",
                            "Expand All",
                        ),
                        on_click=JoinerState.toggle_all_test_results,
                        size="2",
                        color_scheme="indigo",
                        variant="soft",
                    ),
                    spacing="2",
                    align="center",
                ),
                spacing="2",
                align="center",
                justify="between",
                width="100%",
            ),
            # Test results accordion
            rx.box(
                rx.accordion.root(
                    rx.foreach(
                        JoinerState.test_results,
                        lambda result: rx.accordion.item(
                            # Accordion trigger (left row header)
                            header=rx.hstack(
                                rx.badge(
                                    f"Row {result.row_index}",
                                    color_scheme="indigo",
                                    variant="soft",
                                ),
                                rx.text(
                                    f"Left Row #{result.row_index}",
                                    size="2",
                                    weight="medium",
                                ),
                                rx.spacer(),
                                rx.badge(
                                    f"{result.candidates.length()} candidates",
                                    color_scheme="gray",
                                    variant="outline",
                                ),
                                rx.cond(
                                    result.llm_decision is not None,
                                    rx.cond(
                                        result.llm_decision.get("selected") is not None,
                                        rx.icon(
                                            "circle-check", size=16, color="indigo"
                                        ),
                                        rx.icon("x", size=16, color="red"),
                                    ),
                                    rx.fragment(),
                                ),
                                spacing="2",
                                align="center",
                                width="100%",
                            ),
                            # Accordion content (left row details + candidates)
                            content=rx.vstack(
                                # Left row data section
                                rx.vstack(
                                    rx.text(
                                        "Left Row Data:",
                                        size="2",
                                        weight="medium",
                                        color="blue",
                                    ),
                                    rx.box(
                                        rx.hstack(
                                            rx.foreach(
                                                result.left_row.items(),
                                                lambda item: rx.badge(
                                                    f"{item[0]}: {item[1]}",
                                                    color_scheme="blue",
                                                    variant="soft",
                                                ),
                                            ),
                                            wrap="wrap",
                                            spacing="2",
                                        ),
                                        padding="0.5em",
                                        border_radius="6px",
                                        background="var(--blue-a2)",
                                    ),
                                    spacing="2",
                                    width="100%",
                                ),
                                # Candidates section
                                rx.vstack(
                                    rx.text(
                                        "Candidates (Ranked by Score):",
                                        size="2",
                                        weight="medium",
                                        color="green",
                                    ),
                                    rx.cond(
                                        result.candidates.length() > 0,
                                        rx.vstack(
                                            rx.foreach(
                                                result.candidates,
                                                lambda candidate,
                                                idx: render_candidate_card(
                                                    candidate, idx, result
                                                ),
                                            ),
                                            spacing="2",
                                            width="100%",
                                        ),
                                        rx.text(
                                            "No candidates found",
                                            size="2",
                                            color="gray",
                                            style={"fontStyle": "italic"},
                                        ),
                                    ),
                                    spacing="2",
                                    width="100%",
                                ),
                                spacing="3",
                                width="100%",
                            ),
                            value=f"row-{result.row_index}",
                        ),
                    ),
                    type="multiple",
                    default_value=rx.cond(
                        JoinerState.test_results_all_expanded,
                        [
                            f"row-{i}" for i in range(100)
                        ],  # List comprehension for default expanded items
                        [],
                    ),
                    width="100%",
                ),
                max_height="600px",
                overflow_y="auto",
                width="100%",
            ),
            # Cost estimation section
            rx.vstack(
                rx.text("Cost Estimation", size="2", weight="medium"),
                rx.callout(
                    rx.vstack(
                        rx.hstack(
                            rx.text("Test Cost:", weight="medium", size="2"),
                            rx.text(
                                f"${JoinerState.test_cost_total:.4f}",
                                size="2",
                            ),
                            spacing="2",
                            align="center",
                        ),
                        rx.cond(
                            JoinerState.test_mode_type == "full",
                            rx.hstack(
                                rx.text(
                                    "Estimated Full Join Cost:",
                                    weight="medium",
                                    size="2",
                                ),
                                rx.text(
                                    f"${JoinerState.test_cost_estimate:.2f}",
                                    weight="bold",
                                    color="orange",
                                    size="2",
                                ),
                                spacing="2",
                                align="center",
                            ),
                            rx.fragment(),
                        ),
                        rx.text(
                            JoinerState.test_cost_note,
                            size="1",
                            color="gray",
                        ),
                        spacing="1",
                        align="start",
                    ),
                    icon="dollar-sign",
                    color_scheme="indigo",
                    size="2",
                ),
                spacing="2",
                width="100%",
            ),
            spacing="3",
            width="100%",
        ),
        variant="surface",
        size="1",
        width="100%",
    )


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
                    rx.cond(
                        JoinerState.test_mode_enabled,
                        rx.button(
                            rx.icon("flask-conical", size=18),
                            rx.cond(
                                JoinerState.test_mode_type == "dry",
                                "Run Dry Test",
                                "Run Full Test",
                            ),
                            on_click=JoinerState.execute_test_join,
                            size="3",
                            color_scheme="indigo",
                            variant="solid",
                            disabled=~JoinerState.test_can_run,
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
                    ),
                    spacing="4",
                    align="center",
                ),
                spacing="2",
                align="center",
                justify="between",
                width="100%",
            ),
            # Test Mode Toggle Section
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("flask-conical", size=18, color="indigo"),
                        rx.text("Test Mode", size="2", weight="medium"),
                        rx.spacer(),
                        rx.switch(
                            checked=JoinerState.test_mode_enabled,
                            on_change=JoinerState.toggle_test_mode,
                            color_scheme="indigo",
                        ),
                        spacing="2",
                        align="center",
                        justify="between",
                        width="100%",
                    ),
                    rx.text(
                        "Enable test mode to preview join results on a subset of rows before running the full join",
                        size="1",
                        color="gray",
                    ),
                    spacing="1",
                    width="100%",
                ),
                variant="surface",
                size="1",
                width="100%",
            ),
            # Test Configuration Card (conditionally visible)
            rx.cond(
                JoinerState.test_mode_enabled,
                rx.card(
                    rx.vstack(
                        # Card header
                        rx.hstack(
                            rx.icon("flask-conical", size=18, color="indigo"),
                            rx.text("Test Configuration", size="3", weight="bold"),
                            spacing="2",
                            align="center",
                        ),
                        # Test mode type toggle (Dry vs Full)
                        rx.vstack(
                            rx.hstack(
                                rx.text("Test Type:", size="2", weight="medium"),
                                spacing="3",
                                align="center",
                            ),
                            rx.radio_group(
                                ["dry", "full"],
                                value=JoinerState.test_mode_type,
                                on_change=JoinerState.set_test_mode_type,
                                direction="row",
                                spacing="3",
                            ),
                            rx.text(
                                "Dry run shows candidates without LLM calls (free). Full test includes LLM decisions (costs tokens).",
                                size="1",
                                color="gray",
                            ),
                            spacing="2",
                            width="100%",
                        ),
                        # Test size input
                        rx.vstack(
                            rx.hstack(
                                rx.text("Test Size", size="2", weight="medium"),
                                rx.badge(
                                    "Max 100",
                                    color_scheme="indigo",
                                    variant="soft",
                                    size="1",
                                ),
                                spacing="2",
                                align="center",
                            ),
                            rx.text(
                                "Number of left table rows to test with (default: 10)",
                                size="1",
                                color="gray",
                            ),
                            rx.input(
                                type="number",
                                placeholder="10",
                                value=JoinerState.test_size,
                                on_change=JoinerState.set_test_size,
                                size="2",
                                width="200px",
                                min="1",
                                max="100",
                            ),
                            spacing="1",
                            width="100%",
                        ),
                        # WHERE clause input
                        rx.vstack(
                            rx.hstack(
                                rx.text(
                                    "Custom WHERE Clause (Optional)",
                                    size="2",
                                    weight="medium",
                                ),
                                rx.badge(
                                    "Advanced",
                                    color_scheme="indigo",
                                    variant="soft",
                                    size="1",
                                ),
                                spacing="2",
                                align="center",
                            ),
                            rx.text(
                                "Filter which left table rows to test. Leave empty for random selection.",
                                size="1",
                                color="gray",
                            ),
                            rx.text_area(
                                placeholder="Example: category = 'electronics' AND price > 100",
                                value=JoinerState.test_where_clause,
                                on_change=JoinerState.set_test_where_clause,
                                size="2",
                                width="100%",
                                rows="2",
                            ),
                            spacing="1",
                            width="100%",
                        ),
                        # Action buttons row
                        rx.hstack(
                            rx.button(
                                rx.icon("refresh-cw", size=14),
                                "Recalculate Test Rows",
                                on_click=JoinerState.recalculate_test_rows,
                                size="2",
                                color_scheme="indigo",
                                variant="soft",
                                disabled=(JoinerState.left_table == None),
                            ),
                            rx.button(
                                rx.icon("shuffle", size=14),
                                "Shuffle Test Rows",
                                on_click=JoinerState.shuffle_test_rows,
                                size="2",
                                color_scheme="indigo",
                                variant="outline",
                                disabled=(JoinerState.left_table == None),
                            ),
                            spacing="3",
                            align="center",
                        ),
                        # Test row preview section
                        rx.vstack(
                            rx.text("Test Rows Preview", size="2", weight="medium"),
                            rx.cond(
                                JoinerState.current_test_left_sql != "",
                                rx.hstack(
                                    rx.icon("eye", size=16, color="indigo"),
                                    rx.text(
                                        f"{JoinerState.test_size} test rows selected",
                                        size="2",
                                        color="gray",
                                    ),
                                    spacing="2",
                                    align="center",
                                ),
                                rx.hstack(
                                    rx.icon("info", size=16, color="gray"),
                                    rx.text(
                                        "Click 'Recalculate' or 'Shuffle' to select test rows",
                                        size="2",
                                        color="gray",
                                    ),
                                    spacing="2",
                                    align="center",
                                ),
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
                rx.fragment(),
            ),
            # Test Results Panel (conditionally visible)
            rx.cond(
                JoinerState.test_results_available,
                test_results_panel(),
                rx.fragment(),
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
                ~JoinerState.test_mode_enabled,
                # Standard join validation
                rx.cond(
                    ~JoinerState.can_execute_join,
                    rx.callout(
                        rx.vstack(
                            rx.text(
                                "Please complete the following:",
                                weight="bold",
                                size="2",
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
                                    rx.text(
                                        "• Add at least one match criterion", size="2"
                                    ),
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
                # Test mode validation
                rx.cond(
                    ~JoinerState.test_can_run,
                    rx.callout(
                        rx.vstack(
                            rx.text(
                                "Please complete the following:",
                                weight="bold",
                                size="2",
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
                                    rx.text(
                                        "• Add at least one match criterion", size="2"
                                    ),
                                ),
                                rx.cond(
                                    (JoinerState.join_criteria.length() > 0)
                                    & ~JoinerState.has_valid_criteria,
                                    rx.text(
                                        "• Fix matching criteria validation errors",
                                        size="2",
                                        color="red",
                                        weight="medium",
                                    ),
                                ),
                                rx.cond(
                                    JoinerState.join_prompt == "",
                                    rx.text("• Enter join instructions", size="2"),
                                ),
                                rx.cond(
                                    JoinerState.test_size <= 0,
                                    rx.text(
                                        "• Test size must be greater than 0",
                                        size="2",
                                    ),
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
            ),
            spacing="4",
            width="100%",
        ),
        variant="classic",
        width="100%",
    )
