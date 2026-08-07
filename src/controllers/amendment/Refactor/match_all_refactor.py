from __future__ import annotations

import fitz

from src.core.state.app_state import RedactionBox
from src.controllers.amendment.Refactor.match_text_refactor import match_text


def match_all_redactions(
    interpreted_boxes: list[RedactionBox],
    dest_doc: fitz.Document,
    source_page_idx: int,
    page_offset: int = 2,
) -> list[RedactionBox]:
    matched_boxes = []

    for box in interpreted_boxes:
        if box.term == "TEXT":
            matches = match_text(box, dest_doc, source_page_idx, page_offset)
            matched_boxes.extend(matches)
        elif box.term == "TABLE":
            pass
        elif box.term == "DRAWING_CLUSTER":
            pass

    return matched_boxes
