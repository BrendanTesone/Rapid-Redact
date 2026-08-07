from __future__ import annotations

from typing import Callable

import fitz

from src.core.state.app_state import RedactionBox
from src.controllers.amendment.Refactor.extract_refactor import (
    _extract_page_redactions,
)
from src.controllers.amendment.Refactor.interpret_all import interpret_all


def extract_and_interpret_all(
    pdf_path: str, progress_callback: Callable[[int, int, str], None] | None = None
) -> tuple[dict[int, list[RedactionBox]], int]:
    doc = fitz.open(pdf_path)
    all_interpreted: dict[int, list[RedactionBox]] = {}
    total_pages = len(doc)

    for page_idx in range(total_pages):
        if progress_callback:
            progress_callback(
                page_idx + 1,
                total_pages,
                f"Processing page {page_idx + 1} of {total_pages}...",
            )

        page = doc[page_idx]
        raw_boxes = _extract_page_redactions(page, page_idx)
        interpreted_boxes = interpret_all(raw_boxes, page, page_idx)

        if interpreted_boxes:
            all_interpreted[page_idx] = interpreted_boxes

    doc.close()

    return all_interpreted, total_pages


def extract_and_interpret_page(
    pdf_path: str, page_num: int
) -> tuple[list[RedactionBox], int]:
    doc = fitz.open(pdf_path)
    page_idx = page_num - 1

    if page_idx < 0 or page_idx >= len(doc):
        doc.close()
        raise ValueError(f"Page {page_num} out of range (1-{len(doc)} available)")

    page = doc[page_idx]
    raw_boxes = _extract_page_redactions(page, page_idx)
    interpreted_boxes = interpret_all(raw_boxes, page, page_idx)

    doc.close()

    return interpreted_boxes, page_idx
