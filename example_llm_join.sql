-- Example: LLM-powered fuzzy join
-- This demonstrates how to use llm_join() to match rows between two tables

-- First, create some sample data
-- Left table: messy customer data
CREATE OR REPLACE TEMP TABLE customers_raw AS
SELECT * FROM (VALUES
    ('Jon Smith', 'jon.smth@email.com', '2024-01-15'),
    ('Jane Doe', 'j.doe@company.com', '2024-02-20'),
    ('Bob Johnson', 'bob.j@mail.com', '2024-03-10'),
    ('Alice Williams', 'awilliams@example.com', '2024-04-05')
) AS t(name, email, signup_date);

-- Right table: clean customer data
CREATE OR REPLACE TEMP TABLE customers_clean AS
SELECT * FROM (VALUES
    ('John Smith', 'john.smith@email.com', 'C001'),
    ('Jane M. Doe', 'jane.doe@company.com', 'C002'),
    ('Robert Johnson', 'robert.johnson@mail.com', 'C003'),
    ('Alice M. Williams', 'alice.williams@example.com', 'C004')
) AS t(full_name, email_address, customer_id);

-- Perform LLM-powered fuzzy join
-- This will match customers based on name similarity and email similarity
SELECT * FROM llm_join(
    'customers_raw',
    'customers_clean',
    '5: name semantic_distance 2.0, email fuzzy_match 1.5',
    'Match raw customer records to clean customer records. Consider both name similarity (accounting for nicknames and variations) and email address similarity.'
);

-- The result will have columns:
-- left_name, left_email, left_signup_date (from customers_raw)
-- right_full_name, right_email_address, right_customer_id (from customers_clean)
-- join_confidence (0-1 score)
-- join_reasoning (LLM explanation)



