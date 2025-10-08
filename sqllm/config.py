DEFAULT_SQL_QUERY = """-- SQL + LLM Editor
-- Upload a CSV file to get started, then try these LLM-powered queries!

-- Example 1: Ask the LLM a question
SELECT llm('What is the capital of France?') AS answer;

-- Example 2: Interpolate columns into a prompt (printf is concise)
-- SELECT llm(printf('How far apart are %s and %s?', country1, country2)) AS answer
-- FROM your_table_name
-- LIMIT 5;

-- Example 3: Simple concatenation (watch for NULLs)
-- SELECT llm('How far apart are ' || country1 || ' and ' || country2 || '?') AS answer
-- FROM your_table_name
-- LIMIT 5;

-- Example 4: NULL-safe fields with COALESCE
-- SELECT llm(printf('How far apart are %s and %s?', COALESCE(country1, ''), COALESCE(country2, ''))) AS answer
-- FROM your_table_name
-- LIMIT 5;

-- Regular SQL queries work too:
-- SELECT * FROM your_table_name LIMIT 10;
"""
