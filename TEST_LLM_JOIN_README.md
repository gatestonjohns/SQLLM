# LLM Join Test Script

A standalone Python script to test and debug the `llm_join` VTF functionality with detailed output showing exactly what happens at each step.

## Features

- ✅ Load any two CSV files as left and right tables
- ✅ Shows pre-computed similarity scores for all candidates
- ✅ Displays LLM decision-making process for each row
- ✅ Shows what options were presented to the LLM
- ✅ Shows what option (or NULL) the LLM selected
- ✅ Provides detailed reasoning from the LLM
- ✅ Saves final results to CSV file

## Requirements

All dependencies are already in `requirements.txt`. The script uses:

- `duckdb` - for SQL engine
- `pandas` - for data handling
- `sentence-transformers` - for semantic embeddings
- `rapidfuzz` - for fuzzy string matching
- `scikit-learn` - for similarity calculations
- `openai` - for LLM API

Make sure your `OPENAI_API_KEY` environment variable is set.

## Usage

### Basic Usage

```bash
python test_llm_join.py \
    --left test_data_customers_raw.csv \
    --right test_data_customers_clean.csv \
    --algorithm "5: name semantic_distance 2.0, email fuzzy_match 1.5" \
    --prompt "Match raw customer records to clean records based on name and email similarity"
```

### Arguments

- `--left` (required): Path to left table CSV file
- `--right` (required): Path to right table CSV file
- `--algorithm` (required): Algorithm specification string
- `--prompt` (required): Prompt for LLM join decision

### Algorithm Syntax

Format: `k: column mechanism [weight], column mechanism [weight], ...`

- `k`: Maximum number of candidates to show LLM (e.g., `5`)
- `column`: Column name that exists in both tables
- `mechanism`: One of:
  - `semantic_distance` - Embedding-based semantic similarity
  - `fuzzy_match` - Levenshtein edit distance
  - `exact_match` - Binary exact matching
  - `numeric_distance` - Normalized numeric distance
  - `arithmetic_asc` - Rank-based ascending
  - `arithmetic_desc` - Rank-based descending
- `weight`: Optional weight multiplier (defaults to inverse Fibonacci)

## Example Output

The script provides detailed output showing:

### 1. Data Loading

```
=============================================================================
  Loading Data
=============================================================================

Left table:  test_data_customers_raw.csv
Right table: test_data_customers_clean.csv

✓ Loaded 5 rows from left table: test_data_customers_raw
  Columns: id, name, email, signup_date

✓ Loaded 6 rows from right table: test_data_customers_clean
  Columns: full_name, email_address, customer_id, tier
```

### 2. Algorithm Configuration

```
Algorithm string: 5: name semantic_distance 2.0, email fuzzy_match 1.5
Prompt: Match raw customer records to clean records

✓ Parsed algorithm:
  k-value (max candidates): 5
  Criteria:
    1. Column: name
       Mechanism: semantic_distance
       Weight: 2.000
    2. Column: email
       Mechanism: fuzzy_match
       Weight: 1.500
```

### 3. Row-by-Row Processing

```
────────────────────────────────────────────────────────────────────────────
LEFT ROW 1 of 5
────────────────────────────────────────────────────────────────────────────

Left row data:
  id: 1
  name: Jon Smith
  email: jon.smth@email.com
  signup_date: 2024-01-15

→ Finding top 5 candidates from right table...

✓ Found 5 candidates:

Rank   Score    Right Row       Score Breakdown
────────────────────────────────────────────────────────────────────────────
1      0.8234   {'full_name': 'John Smith'...}
       └─ name: 0.9345
       └─ email: 0.8876
2      0.4521   {'full_name': 'Jane M. Doe'...}
       └─ name: 0.5234
       └─ email: 0.4123
...

→ Calling LLM to select best match...

✓ LLM Response:
  Selected candidate: 1
  Confidence: 0.95
  Reasoning: Candidate 1 is the best match. "Jon Smith" closely matches
             "John Smith" (likely a nickname), and the email addresses are
             very similar with only minor typo differences.

  Matched right row:
    full_name: John Smith
    email_address: john.smith@email.com
    customer_id: C001
    tier: Premium
```

### 4. Summary

```
=============================================================================
  SUMMARY
=============================================================================

Total left rows processed: 5
Successful matches:        4 (80.0%)
Null matches:              1 (20.0%)
Average confidence:        0.872

Match breakdown:
  Row 1: ✓ MATCHED (conf: 0.95)
  Row 2: ✓ MATCHED (conf: 0.91)
  Row 3: ✓ MATCHED (conf: 0.88)
  Row 4: ✓ MATCHED (conf: 0.85)
  Row 5: ✗ NULL
```

### 5. Final Result Table

Shows the complete joined table with:

- All `left_*` columns
- All `right_*` columns (or NULL if no match)
- `join_confidence` score
- `join_reasoning` text

Results are also saved to `llm_join_results.csv`

## Example Commands

### Basic Name Matching

```bash
python test_llm_join.py \
    --left test_data_customers_raw.csv \
    --right test_data_customers_clean.csv \
    --algorithm "5: name semantic_distance" \
    --prompt "Match customers by name similarity"
```

### Multi-Criteria with Weights

```bash
python test_llm_join.py \
    --left inventory.csv \
    --right catalog.csv \
    --algorithm "8: product_name semantic_distance 2.0, category exact_match, price numeric_distance" \
    --prompt "Match inventory to catalog. Category must match exactly."
```

### Fuzzy Deduplication

```bash
python test_llm_join.py \
    --left contacts_new.csv \
    --right contacts_existing.csv \
    --algorithm "3: email fuzzy_match 2.0, phone fuzzy_match 1.0" \
    --prompt "Find duplicate contacts based on email and phone"
```

## Output Files

- `llm_join_results.csv` - Final joined results with all columns and metadata

## Troubleshooting

### "No good candidates found"

- Check that column names match between left and right tables
- Verify data types are compatible with the chosen mechanism
- Try increasing the k-value or adjusting weights

### LLM Errors

- Ensure `OPENAI_API_KEY` is set: `export OPENAI_API_KEY=your-key-here`
- Check that you have OpenAI API credits
- Verify internet connection

### Import Errors

- Run from the project root directory: `/Users/gatestonjohns/Documents/SBA/sqllm/`
- Ensure all dependencies are installed: `pip install -r requirements.txt`

## Sample Test Data

The repository includes sample CSV files for testing:

**test_data_customers_raw.csv** - Messy customer data with:

- Nicknames (Jon vs John)
- Typos in emails
- Incomplete information

**test_data_customers_clean.csv** - Clean customer database with:

- Full names
- Correct email addresses
- Customer IDs and tier information

These demonstrate typical fuzzy matching scenarios.

## Tips

1. **Start small**: Test with a few rows first to understand the process
2. **Adjust k-value**: Higher values give LLM more options but cost more
3. **Tune weights**: Higher weights prioritize that criterion
4. **Clear prompts**: Be specific about matching logic and edge cases
5. **Check candidates**: Review what options are being presented to catch issues

## Next Steps

After testing with this script, you can use the same algorithm and prompt in the main application:

```sql
SELECT * FROM llm_join(
    'your_left_table',
    'your_right_table',
    'your_algorithm_string',
    'your_prompt'
);
```


