# no comments below this point

from __future__ import annotations

import fitz

from src.core.state.app_state import RedactionBox, TableRedactionBox
from src.controllers.amendment.Refactor.match_text_refactor import match_text
from src.controllers.amendment.Refactor.match_table_refactor import match_table
from src.controllers.amendment.Refactor.match_drawing_refactor import match_drawing


def match_all(
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
            if isinstance(box, TableRedactionBox):
                matched_box = match_table(box, dest_doc, source_page_idx, page_offset)
                if matched_box:
                    matched_boxes.append(matched_box)
        elif box.term == "DRAWING_CLUSTER":
            matched_box = match_drawing(box, dest_doc, source_page_idx, page_offset)
            if matched_box:
                matched_boxes.append(matched_box)

    return matched_boxes
