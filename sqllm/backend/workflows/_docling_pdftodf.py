from __future__ import annotations
from typing import Any
import pandas as pd
from ..LLM.base import LLMProvider
from docling.document_converter import DocumentConverter, InputFormat, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling_core.types.doc.document import (
    DoclingDocument,
    DocItem,
    GroupItem,
    TextItem,
    TableItem,
    NodeItem,
)
import pdfplumber
from pdfplumber import PDF as PlumberPDF
from docling_core.types.doc.document import ProvenanceItem

import io
import base64
import asyncio
import os
import json
import re
from datetime import datetime

_DEBUG_LOG_DIR = None
_DEBUG_SECTION_COUNTER = 0


def _get_table_markdown_and_b64_img(
    pdfplumber_document: PlumberPDF, prov: ProvenanceItem
) -> tuple[str, str]:
    page = pdfplumber_document.pages[prov.page_no - 1]

    # Convert Docling bbox (Bottom-Left origin) to pdfplumber bbox (Top-Left origin)
    # Docling: t=top (high y), b=bottom (low y) relative to bottom-left
    # pdfplumber: (x0, top, x1, bottom) relative to top-left
    x0 = prov.bbox.l
    top = (
        page.height - prov.bbox.t
    )  # Flip Y: High Docling Y becomes small (top) pdfplumber Y
    x1 = prov.bbox.r
    bottom = (
        page.height - prov.bbox.b
    )  # Flip Y: Low Docling Y becomes large (bottom) pdfplumber Y

    # Crop using the converted coordinates
    cropped_page = page.crop((x0, top, x1, bottom))

    # Get image as bytes, not as file
    image = cropped_page.to_image(resolution=300)
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format="PNG")
    img_byte_arr.seek(0)
    b64_str = base64.b64encode(img_byte_arr.read()).decode("utf-8")

    # Extract ordered text from the cropped region
    words = cropped_page.extract_words()
    words_sorted = sorted(words, key=lambda w: (w["top"], w["x0"]))
    ordered_text = " ".join([w["text"] for w in words_sorted])

    return b64_str, ordered_text


async def _process_table_element(
    llm: LLMProvider,
    pdfplumber_document: PlumberPDF,
    prov: ProvenanceItem,
) -> tuple[str, str]:
    """
    Process a single table element: crop image and get markdown from LLM.
    Returns (markdown_text, b64_image_string).
    """
    new_b64_str, _ = _get_table_markdown_and_b64_img(pdfplumber_document, prov)
    new_table_str = await llm.generate_text_response(
        "Please extract a markdown representation of the table in the image. Do not include any other text in your response.",
        [new_b64_str],
    )
    return new_table_str, new_b64_str


async def _get_relevant_section_content(
    llm: LLMProvider,
    pdfplumber_document: PlumberPDF,
    document_elements: list[NodeItem],
    relevant_section_ranges: list[list[int]],
) -> tuple[str, list[str]]:
    result_str = ""
    b64_imgs: list[str] = []

    # Identify tasks to run in parallel
    pending_tasks = []
    # Store placeholders in the result stream to maintain order
    ordered_results: list[str | asyncio.Task] = []

    for contiguous_range in relevant_section_ranges:
        for element in document_elements[
            contiguous_range[0] : (contiguous_range[1] + 1)
        ]:
            if isinstance(element, TextItem):
                # Text is immediate
                ordered_results.append(element.text)
            elif isinstance(element, TableItem):
                for prov in element.prov:
                    # Tables need async processing
                    task = asyncio.create_task(
                        _process_table_element(llm, pdfplumber_document, prov)
                    )
                    pending_tasks.append(task)
                    ordered_results.append(task)

    # Wait for all table processing to complete
    if pending_tasks:
        await asyncio.gather(*pending_tasks)

    # Assemble final ordered result
    for item in ordered_results:
        if isinstance(item, str):
            result_str += item
        else:
            # It's a completed task returning (markdown, b64_img)
            markdown, img_b64 = item.result()
            result_str += "\n" + markdown + "\n"
            b64_imgs.append(img_b64)

    return result_str, b64_imgs


def _get_docling_document(pdf_path: str) -> DoclingDocument:
    pdf_options = PdfPipelineOptions()
    pdf_options.do_ocr = False  # disable OCR

    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options)}
    )

    result = converter.convert(pdf_path)

    return result.document


def _get_custom_elements_and_tree(
    docling_document: DoclingDocument,
) -> tuple[list[NodeItem], str]:
    texts = []
    for ix, (item, level) in enumerate(docling_document.iterate_items()):
        if isinstance(item, TableItem):
            texts.append(
                "-" * level
                + f"{ix}: {item.label.value} with data as markdown=\n{item.export_to_markdown(docling_document)}"
            )
        elif isinstance(item, GroupItem):
            texts.append(
                "-" * level + f"{ix}: {item.label.value} with name={item.name}"
            )
        elif isinstance(item, TextItem):
            texts.append(
                "-" * level
                + f"{ix}: {item.label.value}: {item.text[: min(len(item.text), 100)]}"
            )
        elif isinstance(item, DocItem):
            texts.append("-" * level + f"{ix}: {item.label.value}")

    return [item for item, _ in docling_document.iterate_items()], "\n".join(texts)


RELEVANT_SECTIONS_JSON_SCHEMA = {
    "schema": {
        "type": "object",
        "properties": {
            "relevant_sections": {
                "type": "array",
                "description": (
                    "List of sections identified as containing data relevant to the extraction task."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "section_title": {
                            "type": "string",
                            "description": "Short title identifying this section (e.g., 'Analysis of Revenues by State', 'Appendix A: Glossary of Terms')",
                        },
                        "ranges": {
                            "type": "array",
                            "description": (
                                "List of inclusive element index ranges. Each range is [start_idx, end_idx]. "
                                "Multiple ranges allow non-contiguous selections. "
                            ),
                            "items": {
                                "type": "array",
                                "minItems": 2,
                                "maxItems": 2,
                                "items": {"type": "integer", "minimum": 0},
                                "additionalProperties": False,
                            },
                            "minItems": 1,
                            "additionalProperties": False,
                        },
                        "condensed_global_context": {
                            "type": "string",
                            "description": (
                                "A synthesized brief description of what this section represents in the context of the overall document and extraction task."
                            ),
                        },
                    },
                    "required": ["section_title", "ranges", "condensed_global_context"],
                    "additionalProperties": False,
                },
                "additionalProperties": False,
            }
        },
        "required": ["relevant_sections"],
        "additionalProperties": False,
    }
}


async def _get_relevant_sections(
    llm: LLMProvider,
    row_json_schema: dict[str, Any],
    user_description: str,
    custom_element_tree: str,
) -> list[dict[str, Any]]:
    prompt = f"""
        You are the first step in a multi-step workflow to extract structured, row-based data from a document.
        Your task is to identify high-level, semantically coherent sections of the document that contain the data necessary to generate rows for the target output table.
        Note: for the sake of context size, please try to ensure that each relevant section is of a digestible size.

        RELEVANCE & GROUPING STRATEGY:
        - **Include by Default:** Err on the side of including anything that seems potentially relevant or useful for generating the correct output.
        - **Exclude if Irrelevant:** Only omit content that is clearly and almost certainly unrelated to the extraction goal.
        - **Group if Related:** If multiple sections are closely related and contain similar information, group them together.
        - **Keep tables together:** If multiple tables are closely related and contain similar information, group them together. Do not split tables across different sections.

        Here is the outline of the table that this entire pipeline aims to extract (therefore you should select all sections that are relevant to the creation of this table):

        {row_json_schema}

        Here is the user's description of the table/how to extract the data to create this table:

        {user_description}

        Here is the document element tree (note that sections have their text truncated if they exceed the preview limit):

        {custom_element_tree}
        """

    if _DEBUG_LOG_DIR is not None:
        debug_subdir = os.path.join(_DEBUG_LOG_DIR, "relevant_sections_determination")
        os.makedirs(debug_subdir, exist_ok=True)
        with open(os.path.join(debug_subdir, "prompt.txt"), "w") as f:
            f.write(prompt)

    relevant_sections = await llm.generate_structured_response(
        prompt,
        RELEVANT_SECTIONS_JSON_SCHEMA,
    )

    if _DEBUG_LOG_DIR is not None:
        debug_subdir = os.path.join(_DEBUG_LOG_DIR, "relevant_sections_determination")
        # Ensure dir exists in case it wasn't created above for some reason (race condition unlikely but safe)
        if os.path.exists(debug_subdir):
            with open(os.path.join(debug_subdir, "response.json"), "w") as f:
                json.dump(relevant_sections, f, indent=2)

    return relevant_sections["relevant_sections"]


async def _single_section_extraction_pass(
    llm: LLMProvider,
    output_table: dict[int, dict],
    row_json_schema: dict[str, Any],
    section_title: str,
    condensed_global_context: str,
    content_str: str,
    b64_png_strings: list[str],
) -> dict[int, dict]:
    global _DEBUG_SECTION_COUNTER
    _DEBUG_SECTION_COUNTER += 1

    prompt = f"""
You are an assistant that is tasked with extracting structured, tabular data from a document.
This extraction process step is a part of a larger, sequential pass over the input document. 
To correctly complete this stage, you will be given a section of the document (in both text and, if applicable, picture form). 
along with the current state of the structured output table.
Your task is to add or update rows on the structured output table (referenced by row number).
Note that the content chunk might have malformed markdown, so please use the provided images to supplement the text when extracting the table.

The current output table:

{output_table}

The title and condensed global context for this section:

SECTION_TITLE: {section_title}

CONDENSED_GLOBAL_CONTEXT: {condensed_global_context}

The content of the current section to extract new or modify existing rows in the output table:

{content_str}
"""
    if _DEBUG_LOG_DIR is not None:
        safe_title = re.sub(r"[^a-zA-Z0-9]", "_", section_title)[:50]
        section_dir = os.path.join(
            _DEBUG_LOG_DIR, f"section_{_DEBUG_SECTION_COUNTER}_{safe_title}"
        )
        os.makedirs(section_dir, exist_ok=True)

        with open(os.path.join(section_dir, "prompt.txt"), "w") as f:
            f.write(prompt)

        for idx, b64_img in enumerate(b64_png_strings):
            try:
                img_data = base64.b64decode(b64_img)
                with open(os.path.join(section_dir, f"image_{idx}.png"), "wb") as f:
                    f.write(img_data)
            except Exception:
                pass

    response = await llm.generate_structured_response(
        prompt,
        {
            "schema": {
                "type": "object",
                "properties": {
                    "rows_to_add_or_update": {
                        "type": "array",
                        "description": "Rows to add new or update in the output table. Each entry must be an object with a 'row_number' (integer, next available number for new rows) and a 'row' object conforming to the provided schema.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "row_number": {
                                    "type": "integer",
                                    "description": "The row number is either a reference to a pre-existing row number for rows to be updated, or in the case of a new row, is the next available row number.",
                                },
                                "row": row_json_schema,
                            },
                            "required": ["row_number", "row"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["rows_to_add_or_update"],
                "additionalProperties": False,
            }
        },
        b64_png_strings,
    )

    if _DEBUG_LOG_DIR is not None:
        safe_title = re.sub(r"[^a-zA-Z0-9]", "_", section_title)[:50]
        section_dir = os.path.join(
            _DEBUG_LOG_DIR, f"section_{_DEBUG_SECTION_COUNTER}_{safe_title}"
        )
        # Note: Directory already created above
        if os.path.exists(section_dir):
            with open(os.path.join(section_dir, "response.json"), "w") as f:
                json.dump(response, f, indent=2)

    return response["rows_to_add_or_update"]


async def pdf_to_dataframe(
    pdf_path: str,
    row_json_schema: dict[str, Any],
    prompt: str,
    *,
    llm,
    tracker=None,  # ProgressTracker
) -> pd.DataFrame:
    global _DEBUG_LOG_DIR
    global _DEBUG_SECTION_COUNTER
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _DEBUG_LOG_DIR = os.path.join("extraction_debug_logs", f"job_{timestamp}")
    _DEBUG_SECTION_COUNTER = 0
    os.makedirs(_DEBUG_LOG_DIR, exist_ok=True)

    output_table: dict[int, dict] = {}

    # Initial Analysis Phase (approx 10% of this task)
    phase_analysis = tracker.add_phase("Analysis", 0.1) if tracker else None
    phase_extraction = tracker.add_phase("Extraction", 0.9) if tracker else None

    if phase_analysis:
        phase_analysis.set_total(1)

    pdfplumber_document = pdfplumber.open(pdf_path)
    # Offload the blocking docling processing to a thread
    docling_document = await asyncio.to_thread(_get_docling_document, pdf_path)

    print(row_json_schema)

    custom_elements, custom_element_tree = _get_custom_elements_and_tree(
        docling_document
    )

    relevant_sections = await _get_relevant_sections(
        llm, row_json_schema, prompt, custom_element_tree
    )

    if phase_analysis:
        phase_analysis.increment()

    # Extraction Phase
    if phase_extraction:
        phase_extraction.set_total(len(relevant_sections))

    for rs in relevant_sections:
        content_str, b64_pngs = await _get_relevant_section_content(
            llm, pdfplumber_document, custom_elements, rs["ranges"]
        )

        response_output_table = await _single_section_extraction_pass(
            llm,
            output_table,
            row_json_schema,
            rs["section_title"],
            rs["condensed_global_context"],
            content_str,
            b64_pngs,
        )

        new_output_table = {
            response_output_table[i]["row_number"]: response_output_table[i]["row"]
            for i in range(len(response_output_table))
        }

        output_table.update(new_output_table)

        if phase_extraction:
            phase_extraction.increment()

    output_table_row_dicts = [
        output_table_row_dict for output_table_row_dict in output_table.values()
    ]

    df = pd.DataFrame.from_records(output_table_row_dicts)

    return df
