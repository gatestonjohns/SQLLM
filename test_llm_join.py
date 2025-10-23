#!/usr/bin/env python3
"""
Test script for llm_join VTF functionality.

Usage:
    python test_llm_join.py \
        --left customers_raw.csv \
        --right customers_clean.csv \
        --algorithm "5: name semantic_distance 2.0, email fuzzy_match 1.5" \
        --prompt "Match raw customer records to clean records based on name and email similarity"
"""

import argparse
import sys
import pandas as pd
import duckdb
from pathlib import Path

# Add sqllm to path
sys.path.insert(0, str(Path(__file__).parent))

from sqllm.backend.Engine.engine import Engine
from sqllm.backend.LLM.OpenAI import OpenAIProvider
from sqllm.backend.VTF.join_algorithm import parse_algorithm, SimilarityScorer
from sqllm.backend.VTF.join_llm import LLMJoinVTF


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def print_subsection(title: str):
    """Print a formatted subsection header."""
    print(f"\n--- {title} ---\n")


def test_llm_join(left_csv: str, right_csv: str, algorithm_str: str, prompt: str):
    """
    Test llm_join functionality with detailed output.

    Args:
        left_csv: Path to left table CSV
        right_csv: Path to right table CSV
        algorithm_str: Algorithm specification (e.g., "5: name semantic_distance")
        prompt: LLM prompt for join decision
    """

    print_section("LLM JOIN TEST")

    # Initialize engine
    print("Initializing engine and LLM provider...")
    conn = duckdb.connect(database=":memory:")
    llm = OpenAIProvider()
    engine = Engine(conn=conn, llm=llm)
    print("✓ Engine initialized\n")

    # Load CSVs
    print_subsection("Loading Data")
    print(f"Left table:  {left_csv}")
    print(f"Right table: {right_csv}")

    left_table_name, _ = engine.load_csv(left_csv)
    right_table_name, _ = engine.load_csv(right_csv)

    left_df = engine.conn.execute(f"SELECT * FROM {left_table_name}").fetchdf()
    right_df = engine.conn.execute(f"SELECT * FROM {right_table_name}").fetchdf()

    print(f"\n✓ Loaded {len(left_df)} rows from left table: {left_table_name}")
    print(f"  Columns: {', '.join(left_df.columns.tolist())}")
    print(f"\n✓ Loaded {len(right_df)} rows from right table: {right_table_name}")
    print(f"  Columns: {', '.join(right_df.columns.tolist())}")

    # Show sample data
    print("\nLeft table preview:")
    print(left_df.head(3).to_string(index=False))
    print("\nRight table preview:")
    print(right_df.head(3).to_string(index=False))

    # Parse algorithm
    print_subsection("Algorithm Configuration")
    print(f"Algorithm string: {algorithm_str}")
    print(f"Prompt: {prompt}\n")

    algorithm = parse_algorithm(algorithm_str)
    print(f"✓ Parsed algorithm:")
    print(f"  k-value (max candidates): {algorithm.k_value}")
    print(f"  Criteria:")
    for i, criterion in enumerate(algorithm.criteria, 1):
        print(f"    {i}. Column: {criterion.column}")
        print(f"       Mechanism: {criterion.mechanism}")
        print(f"       Weight: {criterion.weight:.3f}")

    # Pre-compute similarities
    print_subsection("Pre-computing Similarities")
    print("Computing similarity matrices for all criteria...")
    scorer = SimilarityScorer(left_df, right_df, algorithm.criteria)
    print("✓ Similarity matrices computed and cached")

    # Process each left row
    print_section("JOIN PROCESS - Row by Row")

    vtf = LLMJoinVTF()
    results = []

    for left_idx in range(len(left_df)):
        left_row = left_df.iloc[left_idx].to_dict()

        print(f"\n{'─' * 80}")
        print(f"LEFT ROW {left_idx + 1} of {len(left_df)}")
        print(f"{'─' * 80}")

        # Show left row
        print("\nLeft row data:")
        for key, val in left_row.items():
            print(f"  {key}: {val}")

        # Get candidates
        print(f"\n→ Finding top {algorithm.k_value} candidates from right table...")
        candidates = scorer.get_top_candidates(left_idx, algorithm.k_value)

        if not candidates or candidates[0][1] < 0.01:
            print("\n⚠️  No good candidates found (all scores < 0.01)")
            print("   Skipping LLM call, will return NULL match")
            results.append(
                {
                    "left_row_idx": left_idx,
                    "left_row": left_row,
                    "candidates": [],
                    "selected": None,
                    "confidence": 0.0,
                    "reasoning": "No suitable candidates found",
                }
            )
            continue

        # Display candidates
        print(f"\n✓ Found {len(candidates)} candidates:")
        print(f"\n{'Rank':<6} {'Score':<8} {'Right Row':<15} Score Breakdown")
        print("─" * 80)

        for rank, (right_idx, score, breakdown) in enumerate(candidates, 1):
            right_row = right_df.iloc[right_idx].to_dict()
            right_preview = (
                str(right_row)[:40] + "..."
                if len(str(right_row)) > 40
                else str(right_row)
            )

            print(f"{rank:<6} {score:<8.4f} {right_preview:<15}")
            for col, col_score in breakdown.items():
                print(f"       └─ {col}: {col_score:.4f}")

        # Call LLM
        print(f"\n→ Calling LLM to select best match...")
        candidate_data = []
        for idx, (right_idx, score, breakdown) in enumerate(candidates, 1):
            right_row = right_df.iloc[right_idx].to_dict()
            candidate_data.append(
                {
                    "candidate_number": idx,
                    "row_data": right_row,
                    "combined_score": round(float(score), 3),
                    "score_breakdown": {
                        k: round(float(v), 3) for k, v in breakdown.items()
                    },
                }
            )

        llm_prompt = vtf._build_llm_prompt(left_row, candidate_data, prompt)
        json_schema = vtf._build_response_schema()

        try:
            llm_result = llm.generate_structured_response(llm_prompt, json_schema)

            selected = llm_result.get("selected_candidate")
            confidence = llm_result.get("confidence", 0.0)
            reasoning = llm_result.get("reasoning", "")

            print(f"\n✓ LLM Response:")
            print(f"  Selected candidate: {selected if selected else 'NONE (null)'}")
            print(f"  Confidence: {confidence:.2f}")
            print(f"  Reasoning: {reasoning}")

            if selected is not None:
                selected_idx = int(selected) - 1
                actual_right_idx = candidates[selected_idx][0]
                selected_right_row = right_df.iloc[actual_right_idx].to_dict()
                print(f"\n  Matched right row:")
                for key, val in selected_right_row.items():
                    print(f"    {key}: {val}")

            results.append(
                {
                    "left_row_idx": left_idx,
                    "left_row": left_row,
                    "candidates": candidates,
                    "selected": selected,
                    "confidence": confidence,
                    "reasoning": reasoning,
                    "llm_result": llm_result,
                }
            )

        except Exception as e:
            print(f"\n✗ LLM Error: {str(e)}")
            results.append(
                {
                    "left_row_idx": left_idx,
                    "left_row": left_row,
                    "candidates": candidates,
                    "selected": None,
                    "confidence": 0.0,
                    "reasoning": f"LLM error: {str(e)}",
                }
            )

    # Summary
    print_section("SUMMARY")

    total_rows = len(results)
    matched_rows = sum(1 for r in results if r["selected"] is not None)
    null_rows = total_rows - matched_rows
    avg_confidence = (
        sum(r["confidence"] for r in results) / total_rows if total_rows > 0 else 0
    )

    print(f"Total left rows processed: {total_rows}")
    print(
        f"Successful matches:        {matched_rows} ({matched_rows / total_rows * 100:.1f}%)"
    )
    print(
        f"Null matches:              {null_rows} ({null_rows / total_rows * 100:.1f}%)"
    )
    print(f"Average confidence:        {avg_confidence:.3f}")

    print("\nMatch breakdown:")
    for i, result in enumerate(results):
        status = "✓ MATCHED" if result["selected"] else "✗ NULL"
        conf = f"(conf: {result['confidence']:.2f})" if result["selected"] else ""
        print(f"  Row {i + 1}: {status} {conf}")

    # Create result DataFrame
    print_section("FINAL RESULT TABLE")

    result_rows = []
    for result in results:
        row = {}

        # Add left columns
        for key, val in result["left_row"].items():
            row[f"left_{key}"] = val

        # Add right columns
        if result["selected"] is not None:
            selected_idx = int(result["selected"]) - 1
            actual_right_idx = result["candidates"][selected_idx][0]
            right_row = right_df.iloc[actual_right_idx].to_dict()
            for key, val in right_row.items():
                row[f"right_{key}"] = val
        else:
            for col in right_df.columns:
                row[f"right_{col}"] = None

        # Add metadata
        row["join_confidence"] = result["confidence"]
        row["join_reasoning"] = result["reasoning"]

        result_rows.append(row)

    result_df = pd.DataFrame(result_rows)
    print(result_df.to_string(index=False))

    # Save results
    output_file = "llm_join_results.csv"
    result_df.to_csv(output_file, index=False)
    print(f"\n✓ Results saved to: {output_file}")

    print_section("TEST COMPLETE")


def main():
    parser = argparse.ArgumentParser(
        description="Test llm_join VTF functionality with detailed output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_llm_join.py \\
    --left uploaded_files/customers_raw.csv \\
    --right uploaded_files/customers_clean.csv \\
    --algorithm "5: name semantic_distance 2.0, email fuzzy_match 1.5" \\
    --prompt "Match raw customer records to clean records"
  
  python test_llm_join.py \\
    --left data/inventory.csv \\
    --right data/catalog.csv \\
    --algorithm "8: product_name semantic_distance, category exact_match" \\
    --prompt "Match inventory items to catalog products"
        """,
    )

    parser.add_argument("--left", required=True, help="Path to left table CSV file")

    parser.add_argument("--right", required=True, help="Path to right table CSV file")

    parser.add_argument(
        "--algorithm",
        required=True,
        help='Algorithm specification (e.g., "5: name semantic_distance, email fuzzy_match")',
    )

    parser.add_argument("--prompt", required=True, help="Prompt for LLM join decision")

    args = parser.parse_args()

    # Validate files exist
    if not Path(args.left).exists():
        print(f"Error: Left table file not found: {args.left}")
        sys.exit(1)

    if not Path(args.right).exists():
        print(f"Error: Right table file not found: {args.right}")
        sys.exit(1)

    # Run test
    try:
        test_llm_join(
            left_csv=args.left,
            right_csv=args.right,
            algorithm_str=args.algorithm,
            prompt=args.prompt,
        )
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
