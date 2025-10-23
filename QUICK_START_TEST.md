# Quick Start: Testing LLM Join

Get started testing the new `llm_join` functionality in 3 easy steps!

## Step 1: Set Your OpenAI API Key

```bash
export OPENAI_API_KEY='your-api-key-here'
```

## Step 2: Run the Test Script

### Option A: Use the Quick Test Script (Recommended)

```bash
./run_test_example.sh
```

This will run a pre-configured test with sample customer data.

### Option B: Run Manually with Custom Parameters

```bash
python test_llm_join.py \
    --left test_data_customers_raw.csv \
    --right test_data_customers_clean.csv \
    --algorithm "5: name semantic_distance 2.0, email fuzzy_match 1.5" \
    --prompt "Match raw customer records to clean records"
```

### Option C: Test with Your Own Data

```bash
python test_llm_join.py \
    --left your_left_table.csv \
    --right your_right_table.csv \
    --algorithm "k: col1 mechanism1, col2 mechanism2" \
    --prompt "Your matching instructions"
```

## Step 3: Review the Output

The script will show:

1. ✅ **Data loading** - Confirms tables loaded correctly
2. ✅ **Algorithm parsing** - Shows interpreted criteria and weights
3. ✅ **Similarity computation** - Pre-computes all similarity scores
4. ✅ **Row-by-row processing** - For each left row:
   - Shows the left row data
   - Lists all candidate right rows with scores
   - Shows what the LLM selected and why
   - Displays confidence and reasoning
5. ✅ **Summary statistics** - Match rates and average confidence
6. ✅ **Final result table** - Complete joined output
7. ✅ **Saved CSV** - Results in `llm_join_results.csv`

## Example Output Snippet

```
────────────────────────────────────────────────────────────────────────────
LEFT ROW 1 of 5
────────────────────────────────────────────────────────────────────────────

Left row data:
  id: 1
  name: Jon Smith
  email: jon.smth@email.com

✓ Found 5 candidates:

Rank   Score    Right Row       Score Breakdown
────────────────────────────────────────────────────────────────────────────
1      0.8234   {'full_name': 'John Smith'...}
       └─ name: 0.9345
       └─ email: 0.8876

→ Calling LLM to select best match...

✓ LLM Response:
  Selected candidate: 1
  Confidence: 0.95
  Reasoning: "Jon Smith" closely matches "John Smith" (nickname variation)
```

## Mechanisms Available

Choose from these similarity mechanisms:

| Mechanism           | Best For                   | Example                        |
| ------------------- | -------------------------- | ------------------------------ |
| `semantic_distance` | Text with similar meaning  | "car" ≈ "automobile"           |
| `fuzzy_match`       | Text with typos/variations | "Jon" ≈ "John"                 |
| `exact_match`       | Binary requirements        | Category must be "Electronics" |
| `numeric_distance`  | Number proximity           | $100 ≈ $105                    |
| `arithmetic_asc`    | Ascending rank matching    | Match to next higher value     |
| `arithmetic_desc`   | Descending rank matching   | Match to next lower value      |

## Common Scenarios

### Scenario 1: Name Matching with Typos

```bash
python test_llm_join.py \
    --left messy_contacts.csv \
    --right clean_contacts.csv \
    --algorithm "3: name fuzzy_match" \
    --prompt "Match contacts accounting for typos and spelling variations"
```

### Scenario 2: Multi-Field Deduplication

```bash
python test_llm_join.py \
    --left new_customers.csv \
    --right existing_customers.csv \
    --algorithm "5: email fuzzy_match 2.0, phone fuzzy_match 1.5, name semantic_distance" \
    --prompt "Find duplicates. Prioritize email, then phone, then name."
```

### Scenario 3: Product Matching with Category Requirement

```bash
python test_llm_join.py \
    --left inventory.csv \
    --right catalog.csv \
    --algorithm "8: product_name semantic_distance, category exact_match, price numeric_distance" \
    --prompt "Match inventory to catalog. Category MUST match exactly."
```

## Troubleshooting

**Problem**: "Module not found" error  
**Solution**: Run from project root: `cd /Users/gatestonjohns/Documents/SBA/sqllm/`

**Problem**: "No good candidates found" for all rows  
**Solution**: Check column names match in both CSVs

**Problem**: LLM API error  
**Solution**: Verify `OPENAI_API_KEY` is set and has credits

**Problem**: Slow performance  
**Solution**: Reduce k-value or test with fewer rows first

## What to Look For

When reviewing the output, check:

1. **Are the right candidates being selected?**

   - Look at the candidate rankings
   - Verify scores make sense
   - Check if best match is in top k

2. **Is the LLM making good decisions?**

   - Read the reasoning
   - Verify selected candidate makes sense
   - Check confidence scores

3. **Are weights working correctly?**

   - Higher weighted criteria should dominate scores
   - Adjust weights if priorities are wrong

4. **Are edge cases handled?**
   - NULL matches when appropriate
   - Low confidence on ambiguous cases
   - Exact matches when required

## Next Steps

Once you're satisfied with the test results:

1. Use the same algorithm in your SQL queries:

```sql
SELECT * FROM llm_join(
    'your_table_1',
    'your_table_2',
    'your_tested_algorithm',
    'your_tested_prompt'
);
```

2. Experiment with different:

   - k-values (more candidates = more LLM cost but better accuracy)
   - Weights (tune to your data's priorities)
   - Prompts (guide LLM decision-making)
   - Mechanisms (match your data types)

3. Monitor:
   - Match rates (% of successful joins)
   - Confidence scores (quality of matches)
   - Reasoning (understanding of edge cases)

## Files Created

- `test_llm_join.py` - Main test script
- `run_test_example.sh` - Quick test with sample data
- `test_data_customers_raw.csv` - Sample left table
- `test_data_customers_clean.csv` - Sample right table
- `TEST_LLM_JOIN_README.md` - Detailed documentation

Enjoy fuzzy joining! 🚀


