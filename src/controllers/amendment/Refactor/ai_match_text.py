from __future__ import annotations

from typing import TYPE_CHECKING

import fitz

from src.core.state.app_state import RedactionBox
from src.controllers.amendment.Refactor.ai_transfer_prompt import (
    build_amendment_match_prompt,
    parse_ai_response,
)

if TYPE_CHECKING:
    from src.controllers.ai.llm_client import LiteLLMClient


def ai_match_text_batch(
    text_boxes: list[RedactionBox],
    source_doc: fitz.Document,
    dest_doc: fitz.Document,
    source_page_idx: int,
    page_offset: int,
    llm_client: LiteLLMClient,
) -> list[RedactionBox]:
    """Match TEXT redactions from one source page using AI with configurable search radius."""
    if not text_boxes:
        return []

    dest_start = max(0, source_page_idx - page_offset)
    dest_end = min(len(dest_doc) - 1, source_page_idx + page_offset)
    dest_text = extract_dest_pages_text(dest_doc, dest_start, dest_end)

    print(
        f"      → Sending {len(text_boxes)} texts to AI (pages {dest_start+1}-{dest_end+1})"
    )

    prompt = build_amendment_match_prompt(text_boxes, dest_text, dest_start, dest_end)
    response = llm_client._call_api(prompt, max_tokens=4096)
    matches = parse_ai_response(response)
    print(f"      ← AI returned {len(matches)} potential match(es)")

    matched_boxes = []
    for match in matches:
        boxes = ai_match_to_redaction_boxes(match, dest_doc, text_boxes)
        matched_boxes.extend(boxes)

    return matched_boxes


def extract_dest_pages_text(
    doc: fitz.Document,
    start_page: int,
    end_page: int,
) -> str:
    """Extract text with [PAGE N] markers for AI prompt context."""
    chunks = []
    for page_idx in range(start_page, end_page + 1):
        page = doc[page_idx]
        text = page.get_text("text")
        chunks.append(f"[PAGE {page_idx + 1}]\n{text}\n")

    return "\n".join(chunks)


def ai_match_to_redaction_boxes(
    match: dict[str, object],
    dest_doc: fitz.Document,
    original_boxes: list[RedactionBox],
) -> list[RedactionBox]:
    """Convert AI match to RedactionBox using fuzzy text coordinate search."""
    target_text_obj = match.get("target_text", "")
    page_obj = match.get("page", 0)
    source_text_obj = match.get("source_text", "")

    target_text = str(target_text_obj) if target_text_obj else ""
    page = int(page_obj) if isinstance(page_obj, (int, float, str)) else 0
    source_text = str(source_text_obj) if source_text_obj else ""

    if not target_text or page == 0:
        return []

    original_box = None
    for box in original_boxes:
        if box.match == source_text:
            original_box = box
            break

    if not original_box:
        original_box = original_boxes[0]

    from src.core.domain.ai_detection import find_all_text_coordinates

    pdf_boxes = find_all_text_coordinates(
        pdf_path=dest_doc.name,
        target_text=target_text,
        page_hint=page,
        fuzzy_threshold=0.8,
    )

    result_boxes = []
    for pdf_box in pdf_boxes:
        result_boxes.append(
            RedactionBox(
                id=original_box.id,
                x=pdf_box.x,
                y=pdf_box.y,
                w=pdf_box.w,
                h=pdf_box.h,
                page=page,
                selection_mode=original_box.selection_mode,
                term=original_box.term,
                match=target_text,
                batch_id=original_box.batch_id,
            )
        )

    if len(pdf_boxes) > 1:
        print(
            f"           → Found {len(pdf_boxes)} occurrence(s) of '{target_text[:40]}...'"
        )

    return result_boxes
