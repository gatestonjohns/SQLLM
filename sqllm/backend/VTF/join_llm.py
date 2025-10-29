from __future__ import annotations
import json
import logging
import pandas as pd
from sqlglot import expressions as exp
from typing import Any

from .base import VTFCall
from .join_algorithm import parse_algorithm, SimilarityScorer


class LLMJoinVTF:
    function_name = "llm_join"

    def discover(self, tree: exp.Expression) -> list[VTFCall]:
        """Discover llm_join() calls in the SQL tree."""
        calls: list[VTFCall] = []

        for node in tree.walk(bfs=False):
            if isinstance(node, exp.Func):
                name = node.name.upper() if hasattr(node, "name") else ""
                if name == self.function_name.upper():
                    exprs = node.args.get("expressions", [])
                    if not isinstance(exprs, list):
                        exprs = [exprs] if exprs else []

                    args = [self._literal_value(e) for e in exprs]
                    calls.append(
                        VTFCall(
                            handler=self,
                            args=args,
                            rewrite_to_table=lambda tbl, n=node: self._rewrite_node(
                                n, tbl
                            ),
                        )
                    )

        return calls

    def materialize(self, call: VTFCall, engine) -> str:
        """Execute the LLM join and materialize result table."""
        left_table, right_table, algorithm_str, prompt = self._parse_args(call.args)

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
        table_name = engine._generate_new_table_name("llm_join_result")
        engine._materialize_df(result_df, table_name)

        logging.info(f"llm_join: Materialized {len(result_df)} rows to {table_name}")
        call.rewrite_to_table(table_name)
        return table_name

    def _execute_join(self, left_df, right_df, algorithm, scorer, prompt, llm):
        """Execute the join for all left rows."""
        results = []

        for left_idx in range(len(left_df)):
            left_row = left_df.iloc[left_idx].to_dict()

            # Get top k candidates
            candidates = scorer.get_top_candidates(left_idx, algorithm.k_value)

            # If no good candidates (all scores near 0), skip LLM call
            if not candidates or candidates[0][1] < 0.01:
                results.append(self._create_null_result(left_row, right_df.columns))
                logging.debug(f"llm_join: No good candidates for left row {left_idx}")
                continue

            # Call LLM to pick best match
            llm_result = self._call_llm_for_decision(
                left_row, candidates, right_df, prompt, llm
            )

            # Build result row
            result_row = self._build_result_row(
                left_row, llm_result, right_df, candidates
            )
            results.append(result_row)

        return pd.DataFrame(results)

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

    def _call_llm_for_decision(self, left_row, candidates, right_df, prompt, llm):
        """Call LLM to select best candidate."""
        candidate_data = []
        for idx, (right_idx, score, breakdown) in enumerate(candidates, 1):
            right_row = right_df.iloc[right_idx].to_dict()
            candidate_data.append(
                {
                    "candidate_number": idx,
                    "row_data": self._make_json_serializable(right_row),
                    "combined_score": round(float(score), 3),
                    "score_breakdown": {
                        k: round(float(v), 3) for k, v in breakdown.items()
                    },
                }
            )

        # Convert left_row before passing to prompt builder
        left_row_serializable = self._make_json_serializable(left_row)
        llm_prompt = self._build_llm_prompt(
            left_row_serializable, candidate_data, prompt
        )
        json_schema = self._build_response_schema()

        response = llm.generate_structured_response(llm_prompt, json_schema)
        return response

    def _build_llm_prompt(self, left_row, candidates, user_prompt):
        """Build prompt for LLM decision."""
        return f"""You are helping to perform a fuzzy join between two database tables.

Left table row to match:
{json.dumps(left_row, indent=2)}

Candidate matches from right table (pre-ranked by similarity):
{json.dumps(candidates, indent=2)}

Task: {user_prompt}

Select the candidate number that best matches the left row, or return null if no candidate is a good match.
Provide a very brief (1-2 point, ~20 word) reasoning for your final decision that is formatted as concise reasoning steps as bullet points separated by newlines.
If the decision is obvious, just say why it is obvious in one point. 
If the decision was close, concisely explain how you chose between the top candidates. 
You do not need to mention candidates that were not good matches unless it is a NULL match decision (where no good match was decided)."""

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
                    "reasoning": {
                        "type": "string",
                        "description": "Explanation for the decision",
                    },
                },
                "required": ["selected_candidate", "confidence", "reasoning"],
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
        result["join_reasoning"] = llm_result.get("reasoning", "")

        return result

    def _create_null_result(self, left_row, right_columns):
        """Create result row with no match."""
        result = {f"left_{k}": v for k, v in left_row.items()}
        for col in right_columns:
            result[f"right_{col}"] = None
        result["join_confidence"] = 0.0
        result["join_reasoning"] = "No suitable candidates found"
        return result

    def _parse_args(self, args: list[Any]) -> tuple[str, str, str, str]:
        """Parse function arguments."""
        if len(args) < 4:
            raise ValueError(
                "llm_join requires (left_table, right_table, algorithm, prompt)"
            )
        return args[0], args[1], args[2], args[3]

    def _literal_value(self, e: exp.Expression) -> Any:
        """Extract literal value from expression."""
        if isinstance(e, exp.Literal):
            return e.this
        return e.this

    def _rewrite_node(self, node: exp.Expression, table_name: str) -> None:
        """Rewrite AST node to reference materialized table."""
        table_expr = exp.Table(this=exp.Identifier(this=table_name, quoted=False))
        node.replace(table_expr)
