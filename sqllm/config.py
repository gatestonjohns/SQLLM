DEFAULT_SQL_QUERY = """SELECT *
FROM llm_pdf_to_table(
    'uploaded_files/pdfs/your_pdf.pdf',
    'table antennas (model_name VARCHAR, kg_weight FLOAT, mm_dimensions VARCHAR)',
    'Your task is to extract structured data to represent each of the antenna models of all possible variations. Do not include any information about shipping specifications or any information about hardware that is not an antenna. The goal of this is to extract tabular data for the antenna models supported by this company.'
);
"""
