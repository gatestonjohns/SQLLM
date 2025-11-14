from __future__ import annotations
import json
import logging
import pandas as pd
from sqlglot import expressions as exp
from typing import Any
import concurrent.futures
import uuid

from dev_utils import dev_cache
from .base import VTFCall
from .join_algorithm import parse_algorithm, SimilarityScorer

MAX_ALLOWED_ROWS_FOR_JOIN = 10000


class LLMJoinVTF:
    function_name = "llm_join"  # Primary function name for backward compatibility

    def get_supported_function_names(self):
        """Return list of function names this VTF handles."""
        return ["llm_join", "llm_join_test"]

    def discover(self, tree: exp.Expression) -> list[VTFCall]:
        """Discover llm_join() and llm_join_test() calls in the SQL tree."""
        calls: list[VTFCall] = []
        supported_names = [name.upper() for name in self.get_supported_function_names()]

        for node in tree.walk(bfs=False):
            if isinstance(node, exp.Func):
                name = node.name.upper() if hasattr(node, "name") else ""
                if name in supported_names:
                    exprs = node.args.get("expressions", [])
                    if not isinstance(exprs, list):
                        exprs = [exprs] if exprs else []

                    args = [self._literal_value(e) for e in exprs]
                    # Store the function name in args for later use
                    call = VTFCall(
                        handler=self,
                        args=args,
                        rewrite_to_table=lambda tbl, n=node: self._rewrite_node(n, tbl),
                    )
                    # Store function name as attribute for materialize method
                    call.function_name = name.lower()
                    calls.append(call)

        return calls

    def _dfs_under_allowed_size(self, *dfs: pd.DataFrame) -> bool:
        """
        Check if all dataframes are under the allowed row limit.

        Args:
            *dfs: Any number of pandas DataFrames.

        Returns:
            True if all DataFrames have row count <= MAX_ALLOWED_ROWS_FOR_JOIN, else False.
        """
        return all(len(df) <= MAX_ALLOWED_ROWS_FOR_JOIN for df in dfs)

    def materialize(self, call: VTFCall, engine) -> str:
        """Execute the LLM join or test and materialize result table."""
        # Branch based on function type
        function_name = getattr(call, "function_name", "llm_join")

        if function_name == "llm_join_test":
            return self._materialize_test(call, engine)
        else:
            return self._materialize_join(call, engine)

    def _materialize_join(self, call: VTFCall, engine) -> str:
        """Execute the production LLM join and materialize result table."""
        new_table_name, left_table, right_table, algorithm_str, prompt = (
            self._parse_args(call.args, "llm_join")
        )

        # Parse algorithm
        algorithm = parse_algorithm(algorithm_str)

        # Load tables
        left_sql = (
            f"SELECT * FROM {left_table}"
            if len(left_table.split()) == 1
            else f"({left_table})"
        )
        right_sql = (
            f"SELECT * FROM {right_table}"
            if len(right_table.split()) == 1
            else f"({right_table})"
        )
        left_df = engine.conn.execute(left_sql).fetchdf()
        right_df = engine.conn.execute(right_sql).fetchdf()

        if not self._dfs_under_allowed_size(left_df):
            raise ValueError(
                f"Allowed Cost Threshold Exceeded: Left dataframe is too large to perform per-row LLM join on (max allowed rows: {MAX_ALLOWED_ROWS_FOR_JOIN}). Please reduce the number of rows in the left dataframe."
            )

        # Pre-compute similarities
        logging.info(
            f"llm_join: Pre-computing similarities for {len(left_df)} x {len(right_df)} rows"
        )
        scorer = SimilarityScorer(left_df, right_df, algorithm.criteria)

        # Execute join
        result_df = self._execute_join(
            left_df, right_df, algorithm, scorer, prompt, engine.llm
        )

        # Materialize result
        table_name = engine._generate_new_table_name(new_table_name)
        engine._materialize_df(result_df, table_name, temporary=False)

        logging.info(f"llm_join: Materialized {len(result_df)} rows to {table_name}")
        call.rewrite_to_table(table_name)
        return table_name

    def _materialize_test(self, call: VTFCall, engine) -> str:
        """Execute the test LLM join and materialize test results table."""
        left_table, right_table, algorithm_str, prompt, test_size, test_mode = (
            self._parse_args(call.args, "llm_join_test")
        )

        # Normalize test_size to int
        test_size = int(test_size)

        # Parse algorithm
        algorithm = parse_algorithm(algorithm_str)

        # Build left_sql as a subquery string
        if len(left_table.split()) == 1:
            left_sql = f"SELECT * FROM {left_table}"
        else:
            left_sql = f"({left_table})"

        # Detect if inner SQL already contains LIMIT (case-insensitive)
        if "LIMIT" not in left_sql.upper():
            # Detect if there is a WHERE clause (case-insensitive)
            if "WHERE" not in left_sql.upper():
                # No WHERE clause, use ORDER BY RANDOM() LIMIT
                left_sql = (
                    f"SELECT * FROM ({left_sql}) ORDER BY RANDOM() LIMIT {test_size}"
                )
            else:
                # WHERE clause exists, just add LIMIT
                left_sql = f"SELECT * FROM ({left_sql}) LIMIT {test_size}"

        # Load tables
        right_sql = (
            f"SELECT * FROM {right_table}"
            if len(right_table.split()) == 1
            else f"({right_table})"
        )
        left_df = engine.conn.execute(left_sql).fetchdf()
        right_df = engine.conn.execute(right_sql).fetchdf()

        # Note: Skip size limit check for left_df in test mode (caller handles sampling)

        # Pre-compute similarities
        logging.info(
            f"llm_join_test: Pre-computing similarities for {len(left_df)} x {len(right_df)} rows"
        )
        scorer = SimilarityScorer(left_df, right_df, algorithm.criteria)

        # Execute test join
        result_df = self._execute_test_join(
            left_df, right_df, algorithm, scorer, prompt, engine.llm, test_mode
        )

        # Get final cost stats
        stats = engine.llm.get_current_query_stats()
        logging.info(f"llm_join_test: Total cost: ${stats.get('cost', 0):.4f}")

        # Generate temp table name
        table_name = engine._generate_new_table_name(
            f"__test_join_{uuid.uuid4().hex[:8]}"
        )

        # Materialize test results as temp table
        engine._materialize_df(result_df, table_name, temporary=True)

        logging.info(
            f"llm_join_test: Materialized {len(result_df)} test rows to {table_name}"
        )
        call.rewrite_to_table(table_name)
        return table_name

    def _execute_join(self, left_df, right_df, algorithm, scorer, prompt, llm):
        """Execute the join for all left rows (parallelized)."""
        # Extract columns mentioned in the algorithm criteria
        algorithm_columns = [criterion.column for criterion in algorithm.criteria]

        def process_row(left_idx):
            left_row = left_df.iloc[left_idx].to_dict()

            # Get top k candidates
            candidates = scorer.get_top_candidates(left_idx, algorithm.k_value)

            # If no good candidates (all scores near 0), skip LLM call
            if not candidates or candidates[0][1] < 0.01:
                logging.debug(f"llm_join: No good candidates for left row {left_idx}")
                return self._create_null_result(left_row, right_df.columns)

            # Call LLM to pick best match
            print(f"llm_join: Calling LLM for left row {left_idx}")
            llm_result = self._call_llm_for_decision(
                left_row, candidates, right_df, prompt, llm, algorithm_columns
            )
            print(f"llm_join: Received LLM result for left row {left_idx}")

            # Build result row
            result_row = self._build_result_row(
                left_row, llm_result, right_df, candidates
            )
            return result_row

        # Use ThreadPoolExecutor (or ProcessPoolExecutor if tasks are more cpu-bound)
        with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
            results = list(executor.map(process_row, range(len(left_df))))

        return pd.DataFrame(results)

    def _execute_test_join(
        self, left_df, right_df, algorithm, scorer, prompt, llm, test_mode
    ):
        """Execute test join and return diagnostic data for all left rows (parallelized)."""
        # Extract columns mentioned in the algorithm criteria
        algorithm_columns = [criterion.column for criterion in algorithm.criteria]

        def process_test_row(left_idx):
            left_row = left_df.iloc[left_idx].to_dict()

            # Get top k candidates
            candidates = scorer.get_top_candidates(left_idx, algorithm.k_value)

            # Call LLM if in full test mode and candidates exist
            llm_result = None
            row_cost = 0.0

            if test_mode == "full" and candidates and candidates[0][1] >= 0.01:
                print(f"llm_join_test: Calling LLM for test row {left_idx}")
                llm_result, row_cost = self._call_llm_for_decision_with_cost(
                    left_row, candidates, right_df, prompt, llm, algorithm_columns
                )
                print(f"llm_join_test: Received LLM result for test row {left_idx}")

            # Build test result row
            test_result = self._build_test_result_row(
                left_idx,
                left_row,
                candidates,
                llm_result,
                right_df,
                algorithm_columns,
                test_mode,
                row_cost,
            )
            return test_result

        # Use ThreadPoolExecutor for parallelization
        with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
            results = list(executor.map(process_test_row, range(len(left_df))))

        return pd.DataFrame(results)

    def _build_test_result_row(
        self,
        row_index,
        left_row,
        candidates,
        llm_result,
        right_df,
        algorithm_columns,
        test_mode,
        row_cost,
    ):
        """Build test result row with diagnostic data."""
        # Serialize left_row to JSON
        left_row_json = json.dumps(self._make_json_serializable(left_row))

        # Build candidates_json: array of objects with right_row, score, breakdown
        candidates_list = []
        for right_idx, score, breakdown in candidates:
            right_row = right_df.iloc[right_idx].to_dict()
            # Include full right_row and also filtered right_row_alg_cols
            filtered_right_row = {
                k: v for k, v in right_row.items() if k in algorithm_columns
            }
            candidate_obj = {
                "right_row": self._make_json_serializable(right_row),
                "right_row_alg_cols": self._make_json_serializable(filtered_right_row),
                "score": float(score),
                "breakdown": {k: float(v) for k, v in breakdown.items()},
            }
            candidates_list.append(candidate_obj)

        candidates_json = json.dumps(candidates_list)

        # Build llm_decision_json
        if llm_result is not None:
            llm_decision = {
                "selected": llm_result.get("selected_candidate"),
                "confidence": float(llm_result.get("confidence", 0.0)),
            }
            llm_decision_json = json.dumps(llm_decision)
        else:
            llm_decision_json = None

        return {
            "row_index": row_index,
            "left_row_json": left_row_json,
            "candidates_json": candidates_json,
            "llm_decision_json": llm_decision_json,
            "row_cost": row_cost,
        }

    def _make_json_serializable(self, obj):
        """Convert pandas types to JSON-serializable types."""
        import numpy as np

        if isinstance(obj, dict):
            return {k: self._make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._make_json_serializable(item) for item in obj]
        elif isinstance(obj, (pd.Timestamp, pd.Timedelta)):
            return str(obj)
        elif isinstance(obj, (np.integer, np.floating)):
            return obj.item()
        elif pd.isna(obj):
            return None
        else:
            return obj

    @dev_cache(cache_args=["left_row", "candidates"], cache_delay_seconds=10)
    def _call_llm_for_decision(
        self, left_row, candidates, right_df, prompt, llm, algorithm_columns
    ):
        """Call LLM to select best candidate."""
        # Filter left_row to only include algorithm columns
        filtered_left_row = {
            k: v for k, v in left_row.items() if k in algorithm_columns
        }

        candidate_data = []
        for idx, (right_idx, score, breakdown) in enumerate(candidates, 1):
            right_row = right_df.iloc[right_idx].to_dict()
            # Filter right_row to only include algorithm columns
            filtered_right_row = {
                k: v for k, v in right_row.items() if k in algorithm_columns
            }
            candidate_data.append(
                {
                    "candidate_number": idx,
                    "row_data": self._make_json_serializable(filtered_right_row),
                    "combined_score": round(float(score), 3),
                    "score_breakdown": {
                        k: round(float(v), 3) for k, v in breakdown.items()
                    },
                }
            )

        # Convert filtered left_row before passing to prompt builder
        left_row_serializable = self._make_json_serializable(filtered_left_row)
        llm_prompt = self._build_llm_prompt(
            left_row_serializable, candidate_data, prompt
        )
        json_schema = self._build_response_schema()

        response = llm.generate_structured_response_sync(llm_prompt, json_schema)
        return response

    def _call_llm_for_decision_with_cost(
        self, left_row, candidates, right_df, prompt, llm, algorithm_columns
    ):
        """Call LLM to select best candidate and return per-call cost."""
        # Filter left_row to only include algorithm columns
        filtered_left_row = {
            k: v for k, v in left_row.items() if k in algorithm_columns
        }

        candidate_data = []
        for idx, (right_idx, score, breakdown) in enumerate(candidates, 1):
            right_row = right_df.iloc[right_idx].to_dict()
            # Filter right_row to only include algorithm columns
            filtered_right_row = {
                k: v for k, v in right_row.items() if k in algorithm_columns
            }
            candidate_data.append(
                {
                    "candidate_number": idx,
                    "row_data": self._make_json_serializable(filtered_right_row),
                    "combined_score": round(float(score), 3),
                    "score_breakdown": {
                        k: round(float(v), 3) for k, v in breakdown.items()
                    },
                }
            )

        # Convert filtered left_row before passing to prompt builder
        left_row_serializable = self._make_json_serializable(filtered_left_row)
        llm_prompt = self._build_llm_prompt(
            left_row_serializable, candidate_data, prompt
        )
        json_schema = self._build_response_schema()

        response, usage = llm.generate_structured_response_with_usage_sync(
            llm_prompt, json_schema
        )
        return response, usage["cost"]

    def _build_llm_prompt(self, left_row, candidates, user_prompt):
        """Build prompt for LLM decision."""
        return f"""You are helping to perform a fuzzy join between two database tables.

Left table row to match:
{json.dumps(left_row, indent=2)}

Candidate matches from right table (pre-ranked by similarity):
{json.dumps(candidates, indent=2)}

Task: {user_prompt}

Select the candidate number that best matches the left row, or return null if no candidate is a good match."""

    # Provide a very brief (1-2 point, ~20 word) reasoning for your final decision that is formatted as concise reasoning steps as bullet points separated by newlines.
    # If the decision is obvious, just say why it is obvious in one point.
    # If the decision was close, concisely explain how you chose between the top candidates.
    # You do not need to mention candidates that were not good matches unless it is a NULL match decision (where no good match was decided)."""

    def _build_response_schema(self):
        """Build JSON schema for LLM response."""
        return {
            "name": "JoinDecision",
            "schema": {
                "type": "object",
                "properties": {
                    "selected_candidate": {
                        "type": ["number", "null"],
                        "description": "Candidate number (1-indexed) or null",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence score 0-1",
                    },
                    # TODO: add reasoning back in only for test mode
                    # "reasoning": {
                    #     "type": "string",
                    #     "description": "Explanation for the decision",
                    # },
                },
                "required": ["selected_candidate", "confidence"],  # "reasoning"],
                "additionalProperties": False,
            },
            "strict": True,
        }

    def _build_result_row(self, left_row, llm_result, right_df, candidates):
        """Build final joined row with metadata."""
        result = {}

        # Add left columns
        for key, val in left_row.items():
            result[f"left_{key}"] = val

        # Add right columns (or nulls)
        selected = llm_result.get("selected_candidate")
        if selected is not None:
            # Find the actual right_idx from candidates list
            candidate_idx = int(selected) - 1  # Convert 1-indexed to 0-indexed
            right_idx = candidates[candidate_idx][0]
            right_row = right_df.iloc[right_idx].to_dict()
            for key, val in right_row.items():
                result[f"right_{key}"] = val
        else:
            for col in right_df.columns:
                result[f"right_{col}"] = None

        # Add metadata
        result["join_confidence"] = llm_result.get("confidence", 0.0)
        # result["join_reasoning"] = llm_result.get("reasoning", "")

        return result

    def _create_null_result(self, left_row, right_columns):
        """Create result row with no match."""
        result = {f"left_{k}": v for k, v in left_row.items()}
        for col in right_columns:
            result[f"right_{col}"] = None
        result["join_confidence"] = 0.0
        # result["join_reasoning"] = "No suitable candidates found"
        return result

    def _parse_args(self, args: list[Any], function_name: str):
        """Parse function arguments based on function type."""
        if function_name == "llm_join":
            if len(args) < 5:
                raise ValueError(
                    "llm_join requires (new_table_name, left_table, right_table, algorithm, prompt)"
                )
            return args[0], args[1], args[2], args[3], args[4]
        elif function_name == "llm_join_test":
            if len(args) < 6:
                raise ValueError(
                    "llm_join_test requires (left_table, right_table, algorithm, prompt, test_size, test_mode)"
                )
            return args[0], args[1], args[2], args[3], args[4], args[5]
        else:
            raise ValueError(f"Unknown function name: {function_name}")

    def _literal_value(self, e: exp.Expression) -> Any:
        """Extract literal value from expression."""
        if isinstance(e, exp.Literal):
            return e.this
        return e.this

    def _rewrite_node(self, node: exp.Expression, table_name: str) -> None:
        """Rewrite AST node to reference materialized table."""
        table_expr = exp.Table(this=exp.Identifier(this=table_name, quoted=False))
        node.replace(table_expr)
