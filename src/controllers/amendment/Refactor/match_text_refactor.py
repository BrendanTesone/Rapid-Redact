from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

import fitz
from rapidfuzz import fuzz

from src.core.state.app_state import RedactionBox

if TYPE_CHECKING:
    from src.controllers.ai.llm_client import LiteLLMClient


def match_text(
    text_box: RedactionBox,
    dest_doc: fitz.Document,
    source_page_idx: int,
    page_offset: int = 2,
    threshold: float = 0.80,
    llm_client: LiteLLMClient | None = None,
    source_doc: fitz.Document | None = None,
) -> list[RedactionBox]:
    source_text = text_box.match

    if not source_text or len(source_text) < 3:
        return []

    if llm_client and source_doc:
        from src.controllers.amendment.Refactor.ai_match_text import ai_match_text_batch

        return ai_match_text_batch(
            text_boxes=[text_box],
            source_doc=source_doc,
            dest_doc=dest_doc,
            source_page_idx=source_page_idx,
            page_offset=page_offset,
            llm_client=llm_client,
        )

    return []


def _substring_search_all(
    source_text: str,
    dest_doc: fitz.Document,
    start_page: int,
    end_page: int,
    case_sensitive: bool,
) -> list[tuple[fitz.Rect, int]]:
    results = []

    for page_idx in range(end_page, start_page - 1, -1):
        page = dest_doc[page_idx]

        if case_sensitive:
            matches = page.search_for(source_text)
        else:
            matches = page.search_for(source_text, flags=fitz.TEXT_PRESERVE_WHITESPACE)

        merged_matches = _merge_adjacent_rectangles(matches)

        for match_rect in merged_matches:
            results.append((match_rect, page_idx))

    return results


def _merge_adjacent_rectangles(rects: list[fitz.Rect]) -> list[fitz.Rect]:
    if not rects:
        return []

    sorted_rects = sorted(rects, key=lambda r: (r.y0, r.x0))
    merged = []
    current_group = [sorted_rects[0]]

    for rect in sorted_rects[1:]:
        last_rect = current_group[-1]

        if abs(rect.y0 - last_rect.y0) < 2 and rect.x0 - last_rect.x1 < 5:
            current_group.append(rect)
        else:
            merged.append(_create_bounding_box(current_group))
            current_group = [rect]

    merged.append(_create_bounding_box(current_group))
    return merged


def _create_bounding_box(rects: list[fitz.Rect]) -> fitz.Rect:
    min_x = min(r.x0 for r in rects)
    min_y = min(r.y0 for r in rects)
    max_x = max(r.x1 for r in rects)
    max_y = max(r.y1 for r in rects)
    return fitz.Rect(min_x, min_y, max_x, max_y)


def _fuzzy_search_all(
    source_text: str,
    dest_doc: fitz.Document,
    start_page: int,
    end_page: int,
    threshold: float,
) -> list[tuple[fitz.Rect, int]]:
    doc_id = id(dest_doc)
    results = []

    for page_idx in range(end_page, start_page - 1, -1):
        cached_lines = _extract_page_lines(doc_id, page_idx, dest_doc)

        for line_text, line_bbox in cached_lines:
            score = fuzz.token_set_ratio(source_text, line_text) / 100.0

            if score >= threshold:
                rect = fitz.Rect(line_bbox)
                results.append((rect, page_idx))

    return results


@lru_cache(maxsize=128)
def _extract_page_lines(
    doc_id: int, page_idx: int, dest_doc: fitz.Document
) -> tuple[tuple[str, tuple[float, float, float, float]], ...]:
    page = dest_doc[page_idx]
    text_blocks = page.get_text("dict")
    lines = []

    for block in text_blocks.get("blocks", []):
        if block.get("type") == 0:
            for line in block.get("lines", []):
                line_text = " ".join(
                    span.get("text", "") for span in line.get("spans", [])
                )
                bbox = line.get("bbox")
                if line_text and bbox:
                    lines.append((line_text, bbox))

    return tuple(lines)


def _create_redaction_box(
    text_box: RedactionBox,
    rect: fitz.Rect,
    page_idx: int,
) -> RedactionBox:
    return RedactionBox(
        id=text_box.id,
        x=float(rect.x0),
        y=float(rect.y0),
        w=float(rect.width),
        h=float(rect.height),
        page=page_idx + 1,
        selection_mode=text_box.selection_mode,
        term=text_box.term,
        match=text_box.match,
        batch_id=text_box.batch_id,
    )
