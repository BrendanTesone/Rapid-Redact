"""Split PDF search functions - separate term search and dose detection.

Replaces the unified search_pdfs_generator_with_cci() with focused functions.
"""

from __future__ import annotations

from collections.abc import Generator

import fitz

from src.core.domain.pdf_iteration import (
    get_pdf_files_to_search,
    iterate_pdfs_with_progress,
)
from src.core.domain.pdf_search import preprocess_text
from src.core.domain.pdf_text_position import extract_context_for_rect
from src.core.state.app_state import PdfBox


def search_pdfs_for_terms(
    pdf_folder_path: str,
    active_terms: list[str],
    context_size: int = 50,
    selected_files: list[str] | None = None,
) -> Generator[dict[str, str | int | float | list[PdfBox]], None, None]:
    """Search PDFs for user-defined search terms.

    Args:
        pdf_folder_path: Base folder path for PDFs
        active_terms: List of search terms
        context_size: Number of characters for context extraction
        selected_files: Optional list of specific file paths to search

    Yields:
        Progress dict: {"progress": float, "current_file": str}
        OR Match dict: {"type": "match", "file_name": str, "file_path": str,
                       "page": int, "term": str, "match": str, "context": str,
                       "rects": list[PdfBox]}
        OR Error dict: {"error": str}
    """
    pdf_files = get_pdf_files_to_search(pdf_folder_path, selected_files)
    if not pdf_files:
        yield {"error": "No PDF files found"}
        return

    for item in iterate_pdfs_with_progress(pdf_files):
        if "progress" in item:
            yield item
            continue

        pdf_file = str(item.get("file_name", ""))
        full_path = str(item.get("file_path", ""))
        doc = item.get("doc")
        if not isinstance(doc, fitz.Document):
            continue

        try:
            for page_num, page in enumerate(doc):
                text = str(page.get_text("text"))
                processed_text = preprocess_text(text)

                for term in active_terms:
                    if not term or not str(term).strip():
                        continue

                    ignore_case = getattr(fitz, "TEXT_SEARCH_IGNORECASE", 0)
                    dehyph = getattr(fitz, "TEXT_DEHYPHENATE", 0)
                    flags = ignore_case | dehyph
                    match_quads = (
                        page.search_for(term, flags=flags)
                        if flags
                        else page.search_for(term)
                    )

                    for rect in match_quads:
                        match_text = page.get_textbox(rect).strip()
                        if not match_text:
                            match_text = term

                        context = extract_context_for_rect(
                            page, rect, processed_text, context_size=context_size
                        )

                        yield {
                            "type": "match",
                            "file_name": pdf_file,
                            "file_path": full_path,
                            "page": page_num + 1,
                            "term": str(term),
                            "match": match_text,
                            "context": context,
                            "rects": [
                                PdfBox(
                                    x=rect.x0,
                                    y=rect.y0,
                                    w=rect.width,
                                    h=rect.height,
                                )
                            ],
                        }

        except Exception as e:
            yield {"error": f"Error reading {pdf_file}: {e}"}
        finally:
            doc.close()


def search_pdfs_for_doses(
    pdf_folder_path: str,
    dosing_context_window_words: int = 8,
    selected_files: list[str] | None = None,
) -> Generator[dict[str, str | int | float | list[PdfBox]], None, None]:
    """Search PDFs for dosing patterns (CCI dose detection).

    Args:
        pdf_folder_path: Base folder path for PDFs
        dosing_context_window_words: Window size for dosing context
        selected_files: Optional list of specific file paths to search

    Yields:
        Progress dict: {"progress": float, "current_file": str}
        OR Match dict: {"type": "match", "category": "dosage", "file_name": str,
                       "file_path": str, "page": int, "term": "", "match": str,
                       "context": str, "rects": list[PdfBox]}
        OR Error dict: {"error": str}
    """
    from src.core.domain.cci_detection import _extract_dosing_matches_from_words

    pdf_files = get_pdf_files_to_search(pdf_folder_path, selected_files)
    if not pdf_files:
        yield {"error": "No PDF files found"}
        return

    for item in iterate_pdfs_with_progress(pdf_files):
        if "progress" in item:
            yield item
            continue

        pdf_file = str(item.get("file_name", ""))
        full_path = str(item.get("file_path", ""))
        doc = item.get("doc")
        if not isinstance(doc, fitz.Document):
            continue

        try:
            for page_num, page in enumerate(doc):
                words = page.get_text("words") or []

                # Smart filter always on to reduce false positives
                for dm in _extract_dosing_matches_from_words(
                    words,
                    context_window_words=dosing_context_window_words,
                    smart_filter=True,
                ):
                    yield {
                        "type": "match",
                        "category": "dosage",
                        "file_name": pdf_file,
                        "file_path": full_path,
                        "page": page_num + 1,
                        "term": "CCI:dosing",
                        "match": dm.match,
                        "context": dm.context,
                        "rects": dm.rects,
                    }

        except Exception as e:
            yield {"error": f"Error reading {pdf_file}: {e}"}
        finally:
            doc.close()
