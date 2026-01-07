#!/usr/bin/env python3
"""
PDF to Markdown converter using Docling.

Usage:
    python pdf_to_markdown.py <pdf_path> [-o OUTPUT]

Example:
    python pdf_to_markdown.py document.pdf
    python pdf_to_markdown.py document.pdf -o output.md
"""

import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Convert a PDF to Markdown using Docling."
    )
    parser.add_argument(
        "pdf_path",
        type=str,
        help="Path to the PDF file to convert.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output file path. Default: <pdf_name>.md in current directory.",
    )

    args = parser.parse_args()

    # Validate input file
    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    if not pdf_path.suffix.lower() == ".pdf":
        print(
            f"Warning: File does not have .pdf extension: {pdf_path}", file=sys.stderr
        )

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path.cwd() / f"{pdf_path.stem}.md"

    print(f"Converting: {pdf_path}")
    print(f"Output: {output_path}")
    print()

    from sqllm.backend.PDF.utils import extract_pdf_as_markdown_with_docling

    print("Converting with Docling...")
    markdown = extract_pdf_as_markdown_with_docling(pdf_path=str(pdf_path))

    # Write output
    output_path.write_text(markdown, encoding="utf-8")

    print()
    print(f"✓ Markdown written to: {output_path}")
    print(f"  Size: {len(markdown):,} characters")


if __name__ == "__main__":
    main()
