#!/bin/bash
# Quick test script for llm_join with sample data

echo "========================================"
echo "  LLM Join Test - Customer Matching"
echo "========================================"
echo ""
echo "This will test the llm_join functionality with sample customer data."
echo "Make sure your OPENAI_API_KEY environment variable is set."
echo ""

# Check if OPENAI_API_KEY is set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  Warning: OPENAI_API_KEY not set!"
    echo "   Please export your OpenAI API key:"
    echo "   export OPENAI_API_KEY='your-key-here'"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Run the test
python test_llm_join.py \
    --left test_data_customers_raw.csv \
    --right test_data_customers_clean.csv \
    --algorithm "5: name semantic_distance 2.0, email fuzzy_match 1.5" \
    --prompt "Match raw customer records to clean customer records. Consider both name similarity (accounting for nicknames like Jon vs John) and email address similarity (accounting for typos). Select the candidate that is most likely the same person."

echo ""
echo "========================================"
echo "  Test Complete!"
echo "========================================"
echo ""
echo "Results saved to: llm_join_results.csv"
echo ""



