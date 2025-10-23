-- ============================================================================
-- COMPREHENSIVE EXAMPLE: All LLM Functions in sqllm
-- ============================================================================
-- This file demonstrates all available LLM-powered SQL functions with
-- practical examples showing when and how to use each one.
-- ============================================================================


-- ============================================================================
-- 1. llm() - Scalar UDF for per-row transformations
-- ============================================================================

-- Create sample data
CREATE OR REPLACE TEMP TABLE products AS
SELECT * FROM (VALUES
    (1, 'iPhone 15 Pro Max 256GB', 'Latest Apple smartphone with A17 chip'),
    (2, 'Samsung Galaxy S24 Ultra', 'Premium Android phone with S Pen'),
    (3, 'MacBook Pro 16" M3', 'Professional laptop for developers'),
    (4, 'Dell XPS 15', 'High-performance Windows laptop')
) AS t(id, name, description);

-- Example 1a: Extract brand names
SELECT 
    name,
    llm('Extract just the brand name: ' || name) as brand
FROM products;

-- Example 1b: Classify products into categories
SELECT 
    name,
    llm('Classify this as either "smartphone" or "laptop": ' || name) as category,
    llm('Rate this as "budget", "mid-range", or "premium": ' || name) as price_tier
FROM products;

-- Example 1c: Generate marketing copy
SELECT 
    name,
    llm('Write a 15-word marketing tagline for: ' || name || '. ' || description) as tagline
FROM products;


-- ============================================================================
-- 2. llm_pdf_to_table() - VTF to extract data from PDFs
-- ============================================================================

-- Example 2a: Extract antenna specifications from PDF
SELECT * 
FROM llm_pdf_to_table(
    'uploaded_files/pdfs/antenna_catalog.pdf',
    'table antennas (
        model_name VARCHAR,
        frequency_range VARCHAR,
        gain_db FLOAT,
        weight_kg FLOAT,
        dimensions_mm VARCHAR
    )',
    'Extract all antenna models with their technical specifications. Include model name, frequency range, gain in dB, weight in kg, and dimensions in mm.'
);

-- Example 2b: Extract invoice line items
SELECT *
FROM llm_pdf_to_table(
    'uploaded_files/pdfs/invoice_2024.pdf',
    'TABLE invoice_items (
        line_number INTEGER,
        description VARCHAR,
        quantity INTEGER,
        unit_price FLOAT,
        total_amount FLOAT
    )',
    'Extract all line items from this invoice. Include line number, item description, quantity, unit price, and total amount.'
);


-- ============================================================================
-- 3. llm_table_to_table() - VTF to transform existing tables
-- ============================================================================

-- Example 3a: Enrich products with categories and tags
SELECT *
FROM llm_table_to_table(
    'SELECT name, description FROM products',
    'TABLE enriched_products (
        product_name VARCHAR,
        category VARCHAR,
        subcategory VARCHAR,
        key_features VARCHAR,
        target_audience VARCHAR
    )',
    'For each product, determine: category (smartphones/laptops), subcategory (brand), comma-separated key features, and target audience.'
);

-- Example 3b: Extract structured data from unstructured text
CREATE OR REPLACE TEMP TABLE customer_feedback AS
SELECT * FROM (VALUES
    (1, 'Love the new phone! Great camera, battery lasts all day. A bit expensive though.'),
    (2, 'Terrible experience. Screen broke after 2 weeks. Customer service was unhelpful.'),
    (3, 'Good value for money. Performance is decent, nothing spectacular.')
) AS t(feedback_id, comment);

SELECT *
FROM llm_table_to_table(
    'SELECT feedback_id, comment FROM customer_feedback',
    'TABLE sentiment_analysis (
        feedback_id INTEGER,
        sentiment VARCHAR,
        positive_points VARCHAR,
        negative_points VARCHAR,
        overall_score INTEGER
    )',
    'Analyze each feedback: classify sentiment (positive/negative/neutral), extract positive points, negative points, and give overall score 1-10.'
);


-- ============================================================================
-- 4. llm_join() - VTF for fuzzy joining between tables
-- ============================================================================

-- Create sample tables with messy data
CREATE OR REPLACE TEMP TABLE customers_raw AS
SELECT * FROM (VALUES
    (1, 'Jon Smith', 'jon.smth@email.com', '2024-01-15'),
    (2, 'Jane Doe', 'j.doe@company.com', '2024-02-20'),
    (3, 'Bob Johnson', 'bob.j@mail.com', '2024-03-10'),
    (4, 'Alice Williams', 'awilliams@example.com', '2024-04-05')
) AS t(id, name, email, signup_date);

CREATE OR REPLACE TEMP TABLE customers_clean AS
SELECT * FROM (VALUES
    ('John Smith', 'john.smith@email.com', 'C001', 'Premium'),
    ('Jane M. Doe', 'jane.doe@company.com', 'C002', 'Standard'),
    ('Robert Johnson', 'robert.johnson@mail.com', 'C003', 'Premium'),
    ('Alice M. Williams', 'alice.williams@example.com', 'C004', 'Standard')
) AS t(full_name, email_address, customer_id, tier);

-- Example 4a: Basic fuzzy join on name
SELECT 
    left_id,
    left_name,
    right_full_name,
    right_customer_id,
    join_confidence,
    join_reasoning
FROM llm_join(
    'customers_raw',
    'customers_clean',
    '5: name semantic_distance',
    'Match raw customer records to clean records based on name similarity. Account for nicknames and variations (e.g., Jon vs John).'
);

-- Example 4b: Multi-criteria join with weights
SELECT *
FROM llm_join(
    'customers_raw',
    'customers_clean',
    '5: name semantic_distance 2.0, email fuzzy_match 1.5',
    'Match customers using both name and email. Prioritize name similarity but also consider email matching.'
);


-- ============================================================================
-- ADVANCED EXAMPLES: Combining multiple LLM functions
-- ============================================================================

-- Example 5: Complete workflow - Extract from PDF, enrich, and classify
-- Step 1: Extract product data from PDF
CREATE OR REPLACE TEMP TABLE pdf_products AS
SELECT * FROM llm_pdf_to_table(
    'uploaded_files/pdfs/product_catalog.pdf',
    'table items (name VARCHAR, price FLOAT, description VARCHAR)',
    'Extract all products with name, price, and description'
);

-- Step 2: Enrich with categories using llm_table_to_table
CREATE OR REPLACE TEMP TABLE enriched AS
SELECT * FROM llm_table_to_table(
    'SELECT * FROM pdf_products',
    'TABLE categorized (
        product_name VARCHAR,
        price FLOAT,
        category VARCHAR,
        target_market VARCHAR
    )',
    'Categorize each product and identify target market segment'
);

-- Step 3: Add individual insights using llm()
SELECT
    product_name,
    price,
    category,
    target_market,
    llm('Is this product premium or budget based on: ' || product_name || ' at $' || CAST(price AS VARCHAR)) as price_positioning,
    llm('Write a one-sentence value proposition for: ' || product_name) as value_prop
FROM enriched;


-- ============================================================================
-- PERFORMANCE TIPS
-- ============================================================================

-- Tip 1: Cache results - VTFs reuse tables by default
-- First run creates table:
SELECT * FROM llm_pdf_to_table('file.pdf', 'table data (col VARCHAR)', 'prompt');
-- Second run reuses cached table (fast!)
SELECT * FROM llm_pdf_to_table('file.pdf', 'table data (col VARCHAR)', 'prompt');
-- Force refresh:
SELECT * FROM llm_pdf_to_table('file.pdf', 'table data (col VARCHAR)', 'prompt', '{"force_recreate": true}');

-- Tip 2: Use llm() with filtering to reduce API calls
SELECT name, llm('Classify: ' || name) as category
FROM products
WHERE price > 1000  -- Only classify expensive items
LIMIT 10;  -- Limit for testing

-- Tip 3: Batch similar transformations together
SELECT
    name,
    llm('Extract brand: ' || name) as brand,
    llm('Extract model: ' || name) as model,
    llm('Extract specs: ' || name) as specs
FROM products;  -- More efficient than separate queries


-- ============================================================================
-- END OF EXAMPLES
-- ============================================================================



