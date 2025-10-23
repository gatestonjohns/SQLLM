# sqllm architecture cheat sheet

## runtime flow

- entry `sqllm/sqllm.py` boots Reflex UI, constructs global `Engine`, binds state events (query execute, csv/pdf upload, export)
- Reflex `State.execute_query` -> `Engine.execute` -> DataFrame + warnings; state updates tables list, status messages
- `Engine.execute`: parse SQL with `sqlglot`, let VTF handlers `discover` invocations, for each `materialize` via engine helpers, rewrite AST to concrete table, run DuckDB query, return results
- DuckDB connection lives inside engine; UDFs registered on init; temporary tables created on demand, reused unless caller sets `force_recreate`

## architecture

### core modules

- `sqllm/`
  - `sqllm.py`: Simple Reflex app entry point
  - `state.py`: Centralized state management with global `Engine` instance, handles all UI state transitions
  - `__init__.py`: Module exports for pages and state

### backend modules

- `backend/Engine/`
  - `engine.py`: DuckDB orchestration, materialization helpers, CSV loader, table introspection
  - `schema.py`: parse schema grammar -> canonical spec + JSON schema + pandas dtype map
- `backend/VTF/`
  - `base.py`: VTF protocol (`discover` + `materialize(call, engine)`), `VTFCall` dataclass
  - `pdf_llm.py`: implements `llm_pdf_to_table`; extracts PDF text, builds prompt, calls LLM, coerces rows, materializes temp table, rewrites AST node
  - `table_llm.py`: implements `llm_table_to_table` for table-to-table transformations
  - `join_llm.py`: implements `llm_join` for LLM-powered fuzzy joins between tables
  - `join_algorithm.py`: algorithm parser and similarity scoring for llm_join
  - `register.py`: exports active handler instances
- `backend/LLM/`
  - `base.py`: abstract provider contract (text + structured responses, token counting)
  - `OpenAI.py`: OpenAI Chat Completions integration with JSON schema response format, token limit enforcement
- `backend/PDF/utils.py`: PyMuPDF helpers for pulling full-text per page, warn on low character density
- `backend/UDF/`
  - `base.py`: base class for DuckDB UDFs
  - `llm.py`: `llm` scalar UDF delegating prompts to `OpenAIProvider`
  - `register.py`: registers all bundled UDFs with a DuckDB connection

### frontend modules

- `components/`
  - `gui.py`: Batch PDF processing GUI components with `BatchState` for multi-PDF ingestion workflows
- `pages/`
  - `index.py`: Main page with SQL editor, results display, upload dialogs, and tabbed interface
- `rxconfig.py`: Reflex configuration with TailwindV4 and Sitemap plugins

## data + table lifecycle

- CSV uploads saved under Reflex upload dir, loaded via `Engine.load_csv` -> temp DuckDB table, table list refreshed
- PDF uploads stored for later; `llm_pdf_to_table` references path, engine sanitizes path into table name (deduping with numeric suffixes)
- VTF handler uses schema dtypes to coerce DataFrame, failing fast if LLM response malformed
- Temp tables registered under `CREATE OR REPLACE TEMP TABLE`, dropped when session ends
- Batch processing: `BatchState` manages multi-PDF ingestion with schema builder and configuration options

## key features

### sql editor

- Monaco editor with SQL syntax highlighting
- Real-time query execution with DuckDB
- Results display in data table with export functionality

### file management

- CSV import: Direct upload and table creation
- PDF storage: Upload and reference by path in `llm_pdf_to_table()`
- Table introspection: View available tables with schema and row counts

### batch processing

- Multi-PDF ingestion with custom schema definition
- Interactive schema builder with DuckDB type selection
- Union-based table creation from multiple PDFs
- Optional source tracking and force recreation

### llm integration

- `llm_pdf_to_table()`: VTF - Extract structured data from PDFs using LLM
- `llm_table_to_table()`: VTF - Transform table data using LLM
- `llm_join()`: VTF - LLM-powered fuzzy join between two tables with ranked candidate matching
- `llm()`: UDF - Scalar function for LLM-powered data transformation
- OpenAI integration with token counting and structured responses

## llm function examples

### llm() - Scalar UDF

Perform LLM inference on individual cell values. Useful for enrichment, classification, extraction, and transformation of text data.

```sql
-- Classify customer feedback sentiment
SELECT
    feedback_text,
    llm('Classify this feedback as positive, negative, or neutral: ' || feedback_text) as sentiment
FROM customer_feedback;

-- Extract key information from text
SELECT
    product_name,
    llm('Extract the brand name from: ' || product_name) as brand,
    llm('What category does this product belong to: ' || product_name) as category
FROM products;

-- Generate summaries
SELECT
    article_id,
    llm('Summarize this in 10 words or less: ' || article_text) as summary
FROM articles;

-- Standardize/normalize data
SELECT
    company_name,
    llm('Convert to standard company name format: ' || company_name) as standardized_name
FROM messy_company_data;
```

**Notes**:

- Scalar function, operates row-by-row
- Returns VARCHAR
- NULL-safe (returns NULL on error)
- Can be used in SELECT, WHERE, JOIN conditions, etc.

---

### llm_pdf_to_table() - Virtual Table Function

Extract structured tabular data from PDF documents using LLM vision and understanding.

```sql
-- Extract antenna specifications from PDF
SELECT *
FROM llm_pdf_to_table(
    'uploaded_files/pdfs/antenna_catalog.pdf',
    'table antennas (model_name VARCHAR, kg_weight FLOAT, mm_dimensions VARCHAR, frequency_range VARCHAR)',
    'Extract all antenna models with their specifications. Include model name, weight in kg, dimensions in mm, and frequency range.'
);

-- Extract financial data from invoice
SELECT *
FROM llm_pdf_to_table(
    'uploaded_files/pdfs/invoice_2024.pdf',
    'table line_items (item_description VARCHAR, quantity INTEGER, unit_price FLOAT, total_price FLOAT)',
    'Extract all line items from this invoice including description, quantity, unit price, and total price.'
);

-- Extract equipment list with optional table name
SELECT *
FROM llm_pdf_to_table(
    'uploaded_files/pdfs/equipment_list.pdf',
    'TABLE equipment (equipment_id VARCHAR, manufacturer VARCHAR, model VARCHAR, year INTEGER, condition VARCHAR)',
    'Extract equipment inventory with ID, manufacturer, model, year, and condition assessment.'
);

-- Force recreation of table (re-process PDF)
SELECT *
FROM llm_pdf_to_table(
    'uploaded_files/pdfs/data.pdf',
    'table items (name VARCHAR, value FLOAT)',
    'Extract items and values',
    '{"force_recreate": true}'
);
```

**Arguments**:

1. `pdf_path` (VARCHAR): Path to PDF file
2. `schema` (VARCHAR): Schema definition with optional TABLE name
3. `prompt` (VARCHAR): Instructions for extraction
4. `options` (JSON, optional): Configuration like `{"force_recreate": true}`

**Notes**:

- Results are cached by default (table reused unless `force_recreate: true`)
- Table name auto-generated from PDF filename or explicitly set with `TABLE name (...)`
- Supports all DuckDB types: VARCHAR, INTEGER, BIGINT, DOUBLE, BOOLEAN, DATE, TIMESTAMP

---

### llm_table_to_table() - Virtual Table Function

Transform existing table data using LLM to create a new table with different structure or enriched content.

```sql
-- Enrich product data with categories and tags
SELECT *
FROM llm_table_to_table(
    'SELECT name, description FROM products',
    'TABLE enriched_products (product_name VARCHAR, category VARCHAR, subcategory VARCHAR, tags VARCHAR)',
    'Analyze each product and assign appropriate category, subcategory, and comma-separated tags based on the description.'
);

-- Normalize and standardize addresses
SELECT *
FROM llm_table_to_table(
    'SELECT customer_id, raw_address FROM customers',
    'TABLE clean_addresses (customer_id VARCHAR, street VARCHAR, city VARCHAR, state VARCHAR, zip VARCHAR, country VARCHAR)',
    'Parse the raw address into structured components. Use standard state abbreviations and country names.'
);

-- Extract entities from unstructured text
SELECT *
FROM llm_table_to_table(
    'SELECT article_id, content FROM news_articles',
    'TABLE article_entities (article_id VARCHAR, people VARCHAR, organizations VARCHAR, locations VARCHAR, dates VARCHAR)',
    'Extract named entities: people names, organization names, locations, and dates mentioned. Return comma-separated lists.'
);

-- Aggregate and summarize
SELECT *
FROM llm_table_to_table(
    'SELECT customer_id, array_agg(purchase_description) as purchases FROM orders GROUP BY customer_id',
    'TABLE customer_profiles (customer_id VARCHAR, primary_interest VARCHAR, purchase_frequency VARCHAR, value_tier VARCHAR)',
    'Analyze purchase history to determine primary interest category, estimated purchase frequency, and value tier (high/medium/low).'
);

-- Translation and localization
SELECT *
FROM llm_table_to_table(
    'SELECT product_id, name_en, description_en FROM products',
    'TABLE products_es (product_id VARCHAR, name_es VARCHAR, description_es VARCHAR)',
    'Translate product names and descriptions to Spanish, maintaining technical accuracy.'
);
```

**Arguments**:

1. `source_sql` (VARCHAR): SQL query that produces input data
2. `schema` (VARCHAR): Output schema with TABLE name
3. `prompt` (VARCHAR): Transformation instructions
4. `options` (JSON, optional): Configuration options

**Notes**:

- Input is entire result set from source SQL
- Output schema must include TABLE name
- LLM sees all input rows in context (token limits apply)
- Results cached by table name (use `force_recreate` to regenerate)

---

### llm_join() - Virtual Table Function

Performs an intelligent fuzzy join between two tables using LLM to select the best match from ranked candidates.

```sql
-- Basic fuzzy join with name similarity
SELECT * FROM llm_join(
    'raw_customers',
    'clean_customers',
    '5: name semantic_distance',
    'Match raw customer records to clean records based on name similarity'
);

-- Multi-criteria join with custom weights
SELECT * FROM llm_join(
    'raw_customers',
    'clean_customers',
    '5: name semantic_distance 2.0, email fuzzy_match 1.5',
    'Match raw customer records to clean records, prioritizing name similarity over email matching'
);

-- Product matching with exact category requirement
SELECT * FROM llm_join(
    'inventory',
    'catalog',
    '8: product_name semantic_distance, category exact_match, price numeric_distance',
    'Match inventory items to catalog products. Category must match exactly. Consider product name similarity and price proximity.'
);

-- Deduplication with multiple fuzzy criteria
SELECT * FROM llm_join(
    'contacts_new',
    'contacts_existing',
    '3: email fuzzy_match 2.0, phone fuzzy_match 1.0, company semantic_distance',
    'Find duplicate contacts. Match on email first, then phone, then company name.'
);

-- Time-series matching with temporal ordering
SELECT * FROM llm_join(
    'transactions_unmatched',
    'accounts',
    '10: account_name semantic_distance, transaction_date arithmetic_desc',
    'Match transactions to accounts based on name similarity, preferring more recent transactions'
);
```

**Arguments**:

1. `left_table` (VARCHAR): Name of left table
2. `right_table` (VARCHAR): Name of right table
3. `algorithm` (VARCHAR): Candidate selection algorithm (see below)
4. `prompt` (VARCHAR): Instructions for LLM to select best match

**Algorithm syntax**: `k: column mechanism [weight], ...`

- `k`: Maximum candidates to show LLM (e.g., `5`)
- `column`: Column name that exists in both tables
- `mechanism`: Scoring method (see below)
- `weight`: Optional weight multiplier (default: inverse Fibonacci 1.0, 0.618, 0.382...)

**Mechanisms**:

- `semantic_distance`: Embedding-based semantic similarity (text)
- `fuzzy_match`: Levenshtein edit distance (text)
- `exact_match`: Binary exact match (any type)
- `numeric_distance`: Normalized numeric distance (numbers)
- `arithmetic_asc`: Rank-based ascending order (numbers/dates)
- `arithmetic_desc`: Rank-based descending order (numbers/dates)

**Output columns**:

- `left_*`: All columns from left table (prefixed)
- `right_*`: All columns from right table (prefixed, NULL if no match)
- `join_confidence`: LLM confidence score 0-1
- `join_reasoning`: LLM explanation for decision

**How it works**:

1. For each left row, compute similarity scores using specified mechanisms
2. Combine scores with weights: `score1^weight1 × score2^weight2 × ...`
3. Select top k candidates from right table
4. LLM evaluates candidates and selects best match (or NULL)
5. Return joined results with confidence and reasoning

**Use cases**:

- Data deduplication and record linkage
- Fuzzy matching with messy or inconsistent data
- Entity resolution across datasets
- Matching with nickname/abbreviation variations
- Multi-criteria matching with business logic

---

## quick reference

### All LLM Functions

| Function               | Type | Purpose                             | Key Use Case                                        |
| ---------------------- | ---- | ----------------------------------- | --------------------------------------------------- |
| `llm()`                | UDF  | Scalar LLM inference on cell values | Classification, extraction, enrichment per row      |
| `llm_pdf_to_table()`   | VTF  | Extract structured data from PDFs   | Convert PDF documents to queryable tables           |
| `llm_table_to_table()` | VTF  | Transform/enrich table data         | Restructure, categorize, or translate existing data |
| `llm_join()`           | VTF  | Fuzzy join between tables           | Match records across messy/inconsistent datasets    |

### When to Use Which Function

**Use `llm()`** when:

- Operating on individual cell values
- Need simple text transformation/classification
- Want to use in WHERE clauses or computed columns
- Processing small amounts of text per row

**Use `llm_pdf_to_table()`** when:

- Source data is in PDF format
- Need to extract tables or structured information from documents
- Converting unstructured documents to structured data

**Use `llm_table_to_table()`** when:

- Transforming entire datasets
- Need complex restructuring or enrichment
- LLM needs full context of multiple rows
- Creating derived tables with new schemas

**Use `llm_join()`** when:

- Joining tables without exact match keys
- Dealing with typos, variations, or abbreviations
- Need semantic similarity matching
- Want confidence scores and explanations for matches

---

## extending

- new virtual table: subclass `VirtualTableFunction`, implement `discover`/`materialize`, add instance to `backend/VTF/register.py`
- new UDF: subclass `BaseUDF`, register in `backend/UDF/register.py`
- swap LLM provider: implement `LLMProvider`, pass into `Engine`
- adding ingestion flows: surface via Reflex state events, call engine helpers or add new ones
- new UI components: add to `components/` and import in `pages/index.py`
