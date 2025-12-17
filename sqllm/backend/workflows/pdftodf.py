import asyncio
import json
import pandas as pd
from ..LLM.base import LLMProvider
from ..PDF.utils import extract_full_pdf_text, get_page_annotated_text
from ..Engine.progress import ProgressTracker

ARTIFICIAL_PAGE_BREAK_DELIMITER = "\n<<<< ARTIFICIAL PAGE BREAK DELIMITER FLAG >>>>\n"

DOCUMENT_OUTLINE_JSON_SCHEMA = {
    "schema": {
        "type": "object",
        "properties": {
            "document_outline": {
                "type": "string",
                "description": "A concise, few-sentence executive summary of the document.",
            },
            "document_sections": {
                "type": "array",
                "description": "A list of the high level, contiguous sections in the document along with a brief description of the information contained within each section.",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "section_id": {
                            "type": "string",
                            "description": "A unique identifier for the section. This should be a succinct yet readable string that is easy to remember and unique across the document.",
                            "pattern": "^[a-zA-Z0-9_-]+$",
                        },
                        "section_title": {
                            "type": "string",
                            "description": "The title of the section.",
                        },
                        "section_description": {
                            "type": "string",
                            "description": "A detailed description of what this section represents in the context of the overall document.",
                        },
                    },
                    "required": ["section_id", "section_title", "section_description"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["document_outline", "document_sections"],
        "additionalProperties": False,
    }
}


def _get_relevant_sections_json_schema(section_ids: list[str]) -> dict:
    section_id_pattern = f"^({'|'.join(section_ids)})$"

    return {
        "schema": {
            "type": "object",
            "properties": {
                "relevant_sections": {
                    "type": "array",
                    "description": (
                        "List of sections from the provided list that are identified as containing data relevant to the extraction task. "
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "section_id": {
                                "type": "string",
                                "description": "The unique identifier for the chosen section.",
                                "pattern": section_id_pattern,
                            },
                            "section_inclusion_reasoning": {
                                "type": "string",
                                "description": "A brief description of why this section is relevant to the extraction task.",
                            },
                        },
                        "required": ["section_id", "section_inclusion_reasoning"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["relevant_sections"],
            "additionalProperties": False,
        }
    }


def _get_section_page_ranges_json_schema(section_ids: list[str]) -> dict:
    section_id_pattern = f"^({'|'.join(section_ids)})$"

    return {
        "schema": {
            "type": "object",
            "description": "A mapping between each document section and its corresponding inclusive page range. Adjacent sections may share no more than one page in common (e.g. if a section starts in the middle of a page, both that section and the previous section will include that page in their inclusive page range).",
            "properties": {
                "section_page_ranges": {
                    "type": "array",
                    "description": "A list of mapping objects for each document section and the page range it spans.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "section_id": {
                                "type": "string",
                                "pattern": section_id_pattern,
                                "description": "The unique identifier of a specific document section as seen in the input document outline.",
                            },
                            "page_range": {
                                "type": "object",
                                "description": "The inclusive range of pages that the section spans.",
                                "properties": {
                                    "start_page": {
                                        "type": "integer",
                                        "description": "The first page of the section's content.",
                                    },
                                    "end_page": {
                                        "type": "integer",
                                        "description": "The last page of the section's content.",
                                    },
                                },
                                "required": ["start_page", "end_page"],
                                "additionalProperties": False,
                            },
                        },
                        "required": ["section_id", "page_range"],
                        "additionalProperties": False,
                    },
                    "minItems": 1,
                }
            },
            "required": ["section_page_ranges"],
            "additionalProperties": False,
        }
    }


CHUNKS_FOR_ROW_EXTRACTION_JSON_SCHEMA = {
    "schema": {
        "type": "object",
        "properties": {
            "chunks": {
                "type": "array",
                "description": "A list of chunks to be processed for row extraction. Each chunk is defined by its inclusive range of start and end page numbers. Each chunk should contain the data for one or more rows of the defined output table of the structured data extraction task.",
                "items": {
                    "type": "object",
                    "properties": {
                        "data_extraction_expectation": {
                            "type": "string",
                            "description": "A very concise list of what rows are expected to be extracted from the chunk. Imagine this as a list of the 'primary keys' of the rows that are expected to be extracted from the chunk. Structure this string as a list of comma separated values, e.g. '1, 3, 5'.",
                        },
                        "start_page": {
                            "type": "integer",
                            "description": "The first page of the chunk (inclusive).",
                        },
                        "end_page": {
                            "type": "integer",
                            "description": "The last page of the chunk (inclusive).",
                        },
                    },
                    "required": [
                        "data_extraction_expectation",
                        "start_page",
                        "end_page",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["chunks"],
        "additionalProperties": False,
    }
}


async def _get_doc_outline(llm: LLMProvider, full_pdf_text: str) -> dict:
    return await llm.generate_structured_response(
        f""" 
<ROLE>
You are an administrative assistant that is an expert in document analysis.
</ROLE>

<TASK>
Your task is to create a concise, few-sentence executive summary and high level sections outline for the document that is provided below.
</TASK>

<CRITERIA>
- The summary must include the high level topic of the document and what specific information is contained within the document.
- The sections outline must mirror the document's top-level structure (equivalent to H1 headings or main table of contents entries) and provide a brief description of each section's content.
- Focus only on the highest-level sections (equivalent to main numbered sections in a table of contents, not subsections). For example, include "3. Company Overview" but not "3.1 Business Strategy".
- If the document is quite small and appears to be a single topic, you may return a single section.
- Further segmentation of sections will be performed later, so top level sections are preferred at this stage.
- Non-content sections (table of contents, cover pages, references, glossaries, appendices) should be listed in the sections overview but will be filtered out in later steps as they don't contain extractable data.
</CRITERIA>

<DOCUMENT_OUTLINE>
{full_pdf_text}
</DOCUMENT_OUTLINE>
""",
        DOCUMENT_OUTLINE_JSON_SCHEMA,
    )


async def _get_relevant_sections(
    llm: LLMProvider, doc_outline: dict, TABLE_JSON_SCHEMA: dict, user_instructions: str
) -> dict:
    return await llm.generate_structured_response(
        f""" 
<ROLE>
You are an administrative assistant that is an expert with document analysis.
</ROLE>

<TASK>
Your task is to determine what sections of the document from the attached outline are relevant to the structured data extraction task.
Additionally, use the provided user instructions to determine what sections are relevant to the extraction task.
</TASK>

<CRITERIA>
- Only include sections that contain the data described by the schema below.
- Omit any sections that do not directly contain data that you would expect to be included in the described table output (e.g. tables of contents, appendices, glossaries, etc.).
- Adhere to the provided user instructions.
</CRITERIA>

<STRUCTURED_OUTPUT_SCHEMA>
{json.dumps(TABLE_JSON_SCHEMA, indent=2)}
</STRUCTURED_OUTPUT_SCHEMA>

<USER_INSTRUCTIONS>
{user_instructions}
</USER_INSTRUCTIONS>

<DOCUMENT_OUTLINE>
{json.dumps(doc_outline, indent=2)}
</DOCUMENT_OUTLINE>
""",
        _get_relevant_sections_json_schema(
            [s["section_id"] for s in doc_outline["document_sections"]]
        ),
    )


async def _get_section_page_ranges(
    llm: LLMProvider, doc_outline: dict, page_annotated_text: str
) -> dict:
    return await llm.generate_structured_response(
        f"""
<ROLE>
You are an administrative assistant that is an expert in document analysis and structure.
</ROLE>

<TASK>
Your task is to map each section in the provided document outline to its page range in the document.
To do this, you will be given a document outline and a full text, page-by-page version of the document.
Leverage the descriptions of the sections in the document outline to map each section to its appropriate page range in the document.
</TASK>

<CRITERIA>
- The output should be a list of mappings between each section in the document outline and the page range it spans.
- The list of sections in the document outline is exhaustive.
- All pages should be accounted for in your output.
- Each section in the document outline is contiguous and spans a single, continuous page range.
- Adjacent sections may share no more than one page in common.
</CRITERIA>

<DOCUMENT_OUTLINE>
{json.dumps(doc_outline, indent=2)}
</DOCUMENT_OUTLINE>

<DOCUMENT_PAGES>
{page_annotated_text}
</DOCUMENT_PAGES>
""",
        _get_section_page_ranges_json_schema(
            [s["section_id"] for s in doc_outline["document_sections"]]
        ),
    )


async def _get_chunks_for_row_extraction(
    llm: LLMProvider,
    relevant_section_page_annotated_text: str,
    TABLE_JSON_SCHEMA: dict,
    user_description: str,
) -> dict:
    return await llm.generate_structured_response(
        f"""
<ROLE>
You are an administrative assistant that is an expert in document analysis and structured data extraction.
</ROLE>

<TASK>
Your task is to segment the provided document excerpt into chunks to produce rows in the table defined by the schema below.
Essentially, you are segmenting the document excerpt into a list of chunks, where each chunk contains data for one or more rows of the table.
This segmentation is necessary to ensure that each chunk is processed independently with high attention to detail to ensure that no data is lost. 
You will define each chunk that you determine by specifying the start and end page numbers of the chunk (along with a concise description of what data/rows are expected to be extracted from the chunk).
The end user was also given the opportunity to provide general instructions, which are also provided below and should be considered when defining the chunks.
</TASK>

<CRITERIA>
- Each chunk should contain the data for all columns for one or more rows of the table.
- Each chunk must be one continuous page range.
- Data that is relevant to multiple rows should be included in the same chunk (not split up across multiple chunks).
- Omit any chunks that do not contain any data relevant to the table.
- The list of chunks should be mutually exclusive and cover all data relevant to the table without the risk for duplication downstream.
- Individual chunks should be relatively small (e.g. 1-3 rows of the table per chunk) to ensure that each chunk is processed with high attention to detail.
</CRITERIA>

<TABLE_SCHEMA>
{json.dumps(TABLE_JSON_SCHEMA, indent=2)}
</TABLE_SCHEMA>

<USER_INSTRUCTIONS>
{user_description}
</USER_INSTRUCTIONS>

<DOCUMENT_EXCERPT>
{relevant_section_page_annotated_text}
</DOCUMENT_EXCERPT>
""",
        CHUNKS_FOR_ROW_EXTRACTION_JSON_SCHEMA,
    )


async def _extract_rows_from_chunk(
    llm: LLMProvider,
    chunk_text: str,
    chunk_extraction_expectation: str,
    TABLE_JSON_SCHEMA: dict,
    user_description: str,
) -> dict:
    return await llm.generate_structured_response(
        f"""
<ROLE>
You are an administrative assistant that is an expert in document analysis and structured data extraction.
</ROLE>

<TASK>
Your task is to extract structured data from the provided document excerpt according to the table schema and row extraction hint below.
The document excerpt is simply a text block from the document that contains the data for one or more rows of the table.
The row extraction hint is a list of one or more 'primary keys' for the row(s) you are expected to extract from the document excerpt.
Use the row extraction hint as a guideline for which rows to extract from the document excerpt.
The user was also given the opportunity to provide general instructions, which are also provided below and should be considered when extracting the data.
</TASK>

<CRITERIA>
- Extract the data according to the provided table schema.
- Use the provided extraction hint (which is a list of 'primary keys' for the rows you are expected to extract) to determine which row(s) to extract from the document excerpt.
- You are permitted to slightly deviate from the extraction hint if you believe the extraction hint was not exhaustive.
- Adhere to the provided user instructions.
</CRITERIA>

<TABLE_SCHEMA>
{json.dumps(TABLE_JSON_SCHEMA, indent=2)}
</TABLE_SCHEMA>

<CHUNK_EXTRACTION_EXPECTATION>
{chunk_extraction_expectation}
</CHUNK_EXTRACTION_EXPECTATION>

<USER_INSTRUCTIONS>
{user_description}
</USER_INSTRUCTIONS>

<DOCUMENT_EXCERPT>
{chunk_text}
</DOCUMENT_EXCERPT>
""",
        TABLE_JSON_SCHEMA,
    )


async def pdf_to_dataframe(
    llm: LLMProvider,
    pdf_path: str,
    table_json_schema: dict,
    user_instructions: str,
    tracker: ProgressTracker,
) -> pd.DataFrame:
    # Initialize phases
    phase_planning = tracker.add_phase("Planning", 0.2)
    phase_chunking = tracker.add_phase("Chunking", 0.3)
    phase_extraction = tracker.add_phase("Extraction", 0.5)

    phase_planning.set_total(3)  # Outline, Sections, Page Ranges

    full_pdf_text = extract_full_pdf_text(pdf_path, ARTIFICIAL_PAGE_BREAK_DELIMITER)

    document_outline = await _get_doc_outline(llm, full_pdf_text)
    phase_planning.increment()

    # Prepare input for section_page_ranges before starting tasks
    full_page_annotated_text = get_page_annotated_text(pdf_path)

    # Wrappers for planning tasks to track progress
    async def _tracked_get_relevant_sections():
        res = await _get_relevant_sections(
            llm, document_outline, table_json_schema, user_instructions
        )
        phase_planning.increment()
        return res

    async def _tracked_get_section_page_ranges():
        res = await _get_section_page_ranges(
            llm, document_outline, full_page_annotated_text
        )
        phase_planning.increment()
        return res

    relevant_sections, section_page_ranges = await asyncio.gather(
        _tracked_get_relevant_sections(), _tracked_get_section_page_ranges()
    )

    # Prepare tasks for parallel chunk extraction
    chunk_tasks = []
    num_sections = len(relevant_sections["relevant_sections"])

    if num_sections == 0:
        phase_chunking.set_total(1)
        phase_chunking.increment()
    else:
        phase_chunking.set_total(num_sections)

    async def _tracked_get_chunks(rs_page_annotated_text):
        res = await _get_chunks_for_row_extraction(
            llm, rs_page_annotated_text, table_json_schema, user_instructions
        )
        phase_chunking.increment()
        return res

    for rs in relevant_sections["relevant_sections"]:
        rs_page_range: tuple[int, int] = [
            (s["page_range"]["start_page"], s["page_range"]["end_page"])
            for s in section_page_ranges["section_page_ranges"]
            if rs["section_id"] == s["section_id"]
        ][0]
        rs_page_annotated_text = get_page_annotated_text(
            pdf_path, rs_page_range[0], rs_page_range[1]
        )

        chunk_tasks.append(_tracked_get_chunks(rs_page_annotated_text))

    chunks_results = await asyncio.gather(*chunk_tasks)

    chunks_for_row_extraction = []
    for res in chunks_results:
        chunks_for_row_extraction.extend(res["chunks"])

    # Prepare tasks for parallel row extraction
    row_tasks = []
    num_chunks = len(chunks_for_row_extraction)

    if num_chunks == 0:
        phase_extraction.set_total(1)
        phase_extraction.increment()
    else:
        phase_extraction.set_total(num_chunks)

    async def _tracked_extract_rows(chunk_text, expectation):
        res = await _extract_rows_from_chunk(
            llm,
            chunk_text,
            expectation,
            table_json_schema,
            user_instructions,
        )
        phase_extraction.increment()
        return res

    for chunk in chunks_for_row_extraction:
        chunk_text = get_page_annotated_text(
            pdf_path, chunk["start_page"], chunk["end_page"]
        )
        row_tasks.append(
            _tracked_extract_rows(chunk_text, chunk["data_extraction_expectation"])
        )

    row_results = await asyncio.gather(*row_tasks)

    all_rows = []
    for res in row_results:
        all_rows.extend(res["rows"])

    return pd.DataFrame(all_rows).drop_duplicates()
