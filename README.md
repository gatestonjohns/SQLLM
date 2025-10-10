# sqllm architecture cheat sheet

## runtime flow

- entry `sqllm/sqllm.py` boots Reflex UI, constructs global `Engine`, binds state events (query execute, csv/pdf upload, export)
- Reflex `State.execute_query` -> `Engine.execute` -> DataFrame + warnings; state updates tables list, status messages
- `Engine.execute`: parse SQL with `sqlglot`, let VTF handlers `discover` invocations, for each `materialize` via engine helpers, rewrite AST to concrete table, run DuckDB query, return results
- DuckDB connection lives inside engine; UDFs registered on init; temporary tables created on demand, reused unless caller sets `force_recreate`

## packages

- `Engine/`
  - `engine.py`: DuckDB orchestration, materialization helpers, CSV loader, table introspection
  - `schema.py`: parse schema grammar -> canonical spec + JSON schema + pandas dtype map
- `VTF/`
  - `base.py`: VTF protocol (`discover` + `materialize(call, engine)`), `VTFCall` dataclass
  - `pdf_llm.py`: implements `llm_pdf_to_table`; extracts PDF text, builds prompt, calls LLM, coerces rows, materializes temp table, rewrites AST node
  - `register.py`: exports active handler instances
- `LLM/`
  - `base.py`: abstract provider contract (text + structured responses, token counting)
  - `OpenAI.py`: OpenAI Chat Completions integration with JSON schema response format, token limit enforcement
- `PDF/utils.py`: PyMuPDF helpers for pulling full-text per page, warn on low character density
- `UDF/`
  - `base.py`: base class for DuckDB UDFs
  - `llm.py`: `llm` scalar UDF delegating prompts to `OpenAIProvider`
  - `register.py`: registers all bundled UDFs with a DuckDB connection
- root `sqllm.py`: Reflex UI definitions (editor, results grid, uploads), state transitions, downloads
- `config.py`: UI defaults (initial SQL)

## data + table lifecycle

- CSV uploads saved under Reflex upload dir, loaded via `Engine.load_csv` -> temp DuckDB table, table list refreshed
- PDF uploads stored for later; `llm_pdf_to_table` references path, engine sanitizes path into table name (deduping with numeric suffixes)
- VTF handler uses schema dtypes to coerce DataFrame, failing fast if LLM response malformed
- Temp tables registered under `CREATE OR REPLACE TEMP TABLE`, dropped when session ends

## extending

- new virtual table: subclass `VirtualTableFunction`, implement `discover`/`materialize`, add instance to `VTF/register.py`
- new UDF: subclass `BaseUDF`, register in `UDF/register.py`
- swap LLM provider: implement `LLMProvider`, pass into `Engine`
- adding ingestion flows: surface via Reflex state events, call engine helpers or add new ones
