"""
State-focused text selection handling.

Architectural note: This module handles STATE updates only.
Rendering is delegated to SelectionRenderer to maintain separation of concerns.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import flet as ft

from src.core.state.app_state import RedactionBox
from src.core.state.selection_state import (
    SelectionRange,
    TextSelection,
)
from src.interaction.refact_text_selection import (
    Character,
)

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class TextStructure:
    """Text structure extracted from a PDF page for text selection."""

    line_chars: dict[tuple[int, int], list[Character]]
    line_bounds: dict[tuple[int, int], tuple[float, float]]


class ViewerProtocol(Protocol):
    def navigate_to_page(self, file_path: str, page_num: int) -> None: ...
    def _refresh_all_rendered_overlays(self) -> None: ...


class RedactionDataProtocol(Protocol):
    def add_redaction_batch(
        self, boxes: list[RedactionBox], page_index: int
    ) -> None: ...


class ControllerProtocol(Protocol):
    redaction_data: "RedactionDataProtocol"
    viewer: "ViewerProtocol"


def handle_pan_end_redact(
    e: ft.DragEndEvent,
    page_index: int,
    selection: TextSelection,
    controller: ControllerProtocol,
) -> None:
    file_path = selection.file_path
    if selection.range and selection.range.spans:
        boxes = convert_selection_to_redactions(selection.range, page_index, file_path)
        if boxes:
            controller.redaction_data.add_redaction_batch(boxes, page_index)
    selection.collapse()
    controller.viewer._refresh_all_rendered_overlays()


def handle_pan_end_highlight_only(
    e: ft.DragEndEvent,
    page_index: int,
    selection: TextSelection,
    controller: ControllerProtocol,
) -> None:
    """Highlight mode: collapses selection without creating redactions."""
    selection.collapse()
    controller.viewer._refresh_all_rendered_overlays()


def convert_selection_to_redactions(
    selection_range: SelectionRange, page_index: int, file_path: str | None = None
) -> list[RedactionBox]:
    """Convert selection range to redaction boxes. All boxes share the same batch_id for grouped operations."""
    if not selection_range.spans:
        return []

    batch_id = str(uuid.uuid4())
    boxes: list[RedactionBox] = []

    section_title: str | None = None
    if file_path:
        from src.core.domain.toc_util import get_section_title_for_page

        section_title = get_section_title_for_page(file_path, page_index + 1)

    match_text = " ".join(span.text for span in selection_range.spans)

    for span in selection_range.spans:
        box = RedactionBox(
            id=str(uuid.uuid4()),
            x=span.x0,
            y=span.y0,
            w=span.x1 - span.x0,
            h=span.y1 - span.y0,
            page=page_index,
            batch_id=batch_id,
            is_repeat_draft=False,
            match=match_text,
            section_title=section_title,
        )
        boxes.append(box)

    return boxes
