from __future__ import annotations


import fitz

from src.core.state.app_state import RedactionBox
from src.controllers.amendment.Refactor.interpret_text_refactor import interpret_text


def interpret_all(
    raw_boxes: list[RedactionBox], page: fitz.Page, page_idx: int
) -> list[RedactionBox]:
    interpreted_boxes = []

    for raw_box in raw_boxes:
        text_boxes = interpret_text(raw_box, page, page_idx)
        interpreted_boxes.extend(text_boxes)

    return interpreted_boxes
