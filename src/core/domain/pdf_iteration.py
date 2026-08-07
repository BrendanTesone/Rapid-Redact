"""PDF iteration utilities for search operations.

Shared infrastructure for iterating through PDFs with progress reporting.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import fitz


def get_pdf_files_to_search(
    pdf_folder_path: str,
    selected_files: list[str] | None = None,
) -> list[tuple[str, str]]:
    """Get list of PDF files to search.

    Args:
        pdf_folder_path: Base folder path for PDFs
        selected_files: Optional list of specific file paths to search

    Returns:
        List of (basename, full_path) tuples for PDFs to process
    """
    pdf_files_with_paths: list[tuple[str, str]] = []

    if selected_files:
        for file_path in selected_files:
            if os.path.isfile(file_path) and file_path.lower().endswith(".pdf"):
                pdf_files_with_paths.append((os.path.basename(file_path), file_path))
    else:
        if not os.path.exists(pdf_folder_path):
            return []
        all_files = os.listdir(pdf_folder_path)
        for filename in all_files:
            if filename.lower().endswith(".pdf"):
                full_path = os.path.join(pdf_folder_path, filename)
                if os.path.isfile(full_path):
                    pdf_files_with_paths.append((filename, full_path))

    return pdf_files_with_paths


def iterate_pdfs_with_progress(
    pdf_files_with_paths: list[tuple[str, str]],
) -> Generator[dict[str, str | int | float | fitz.Document], None, None]:
    """Iterate through PDFs with progress reporting.

    Yields progress updates and opened PDF documents.

    Args:
        pdf_files_with_paths: List of (basename, full_path) tuples

    Yields:
        Progress dict: {"progress": float, "current_file": str}
        OR Document dict: {"type": "document", "file_name": str, "file_path": str, "doc": fitz.Document}
    """
    total_files = len(pdf_files_with_paths)

    for idx, (pdf_file, full_path) in enumerate(pdf_files_with_paths):
        progress = idx / total_files if total_files > 0 else 0.0
        yield {
            "progress": progress,
            "current_file": pdf_file,
        }

        try:
            doc = fitz.open(full_path)
            yield {
                "type": "document",
                "file_name": pdf_file,
                "file_path": full_path,
                "doc": doc,
            }
        except Exception:
            continue
