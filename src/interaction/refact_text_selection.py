from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, NamedTuple

import fitz
import flet as ft

from src.core.state.selection_state import (
    SelectionPoint,
    SelectionRange,
    SelectionSpan,
    TextSelection,
)

if TYPE_CHECKING:
    from src.core.state.app_state import ViewerState

BULLET_CHARS: frozenset[str] = frozenset("•▪◦·–—-​‐")
SINGLE_LINE_SELECTION_TOLERANCE: float = 2.0


class CellBoundingBox(NamedTuple):
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class Character:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass(frozen=True)
class TextLine:
    y_top: float
    y_bottom: float
    characters: list[Character]

    def contains_y(self, y: float) -> bool:
        return self.y_top <= y <= self.y_bottom

    def find_character_at_x(self, x: float) -> Character | None:
        for char in self.characters:
            if char.x0 <= x <= char.x1:
                return char
        return None

    def get_characters_in_x_range(
        self, x_start: float, x_end: float
    ) -> list[Character]:
        return [
            char for char in self.characters if x_start <= char.center_x <= x_end
        ]

    @property
    def center_y(self) -> float:
        return (self.y_top + self.y_bottom) / 2


@dataclass(frozen=True)
class PageText:
    lines: list[TextLine]

    def find_line_at_y(self, y: float) -> TextLine | None:
        for line in self.lines:
            if line.contains_y(y):
                return line
        return None

    def find_lines_in_y_range(
        self, y_start: float, y_end: float, tolerance: float = 0.0
    ) -> list[TextLine]:
        affected = [
            line
            for line in self.lines
            if y_start - tolerance <= line.center_y <= y_end + tolerance
        ]
        return sorted(affected, key=lambda ln: ln.y_top)


def handle_pan_start(
    e: ft.DragStartEvent,
    page_index: int,
    selection: TextSelection,
    viewer: ViewerState,
) -> None:
    if not viewer.file_path:
        return

    point: SelectionPoint = raw_point_to_snapped_selection_point(
        float(e.local_x),
        float(e.local_y),
        page_index,
        viewer.file_path,
        viewer.scale_factors.get(page_index, 1.0),
    )

    selection.set_start_and_page_index(point, page_index)
    selection.set_focus(point)
    selection.file_path = viewer.file_path


def handle_pan_update(
    e: ft.DragUpdateEvent,
    page_index: int,
    selection: TextSelection,
    viewer: ViewerState,
) -> None:
    if not selection.is_active or not selection.file_path or not viewer.file_path:
        return

    point: SelectionPoint = raw_point_to_snapped_selection_point(
        float(e.local_x),
        float(e.local_y),
        page_index,
        selection.file_path,
        viewer.scale_factors.get(page_index, 1.0),
    )

    selection.set_focus(point)
    compute_selection_range(selection, selection.file_path, page_index)


def compute_selection_range(
    selection: TextSelection, file_path: str, page_index: int
) -> None:
    if not selection.start or not selection.focus:
        return

    page_text: PageText | None = extract_page_text(file_path, page_index)
    if not page_text:
        return

    focus_x: float = selection.focus.x
    focus_y: float = selection.focus.y
    anchor_x: float = selection.start.x
    anchor_y: float = selection.start.y

    is_vertical_backward: bool = focus_y < anchor_y
    is_same_line: bool = abs(focus_y - anchor_y) < SINGLE_LINE_SELECTION_TOLERANCE
    is_horizontal_backward: bool = focus_x < anchor_x
    is_backward_on_same_line: bool = is_same_line and is_horizontal_backward
    is_backward_selection: bool = is_vertical_backward or is_backward_on_same_line

    if is_backward_selection:
        sel_start_x, sel_start_y = focus_x, focus_y
        sel_end_x, sel_end_y = anchor_x, anchor_y
    else:
        sel_start_x, sel_start_y = anchor_x, anchor_y
        sel_end_x, sel_end_y = focus_x, focus_y

    anchor_cell: CellBoundingBox | None = cell_containing_point(
        extract_table_cells(file_path, page_index), anchor_x, anchor_y
    )
    cell_x0: float = -float("inf")
    cell_x1: float = float("inf")
    if anchor_cell:
        cell_x0, cell_x1 = anchor_cell.x0, anchor_cell.x1
        sel_start_x = max(anchor_cell.x0, min(anchor_cell.x1, sel_start_x))
        sel_start_y = max(anchor_cell.y0, min(anchor_cell.y1, sel_start_y))
        sel_end_x = max(anchor_cell.x0, min(anchor_cell.x1, sel_end_x))
        sel_end_y = max(anchor_cell.y0, min(anchor_cell.y1, sel_end_y))

    tolerance: float = SINGLE_LINE_SELECTION_TOLERANCE if is_same_line else 0.0

    affected_lines: list[TextLine] = page_text.find_lines_in_y_range(
        sel_start_y, sel_end_y, tolerance
    )
    if not affected_lines:
        selection.set_range(
            SelectionRange(
                SelectionPoint(x=sel_start_x, y=sel_start_y),
                SelectionPoint(x=sel_end_x, y=sel_end_y),
                [],
            )
        )
        return

    spans: list[SelectionSpan] = []
    first_span_found: bool = False
    first_line_start: float = sel_start_x
    last_line_end: float = sel_end_x
    last_span: SelectionSpan | None = None

    for line_index, line in enumerate(affected_lines):
        is_first_line: bool = line_index == 0
        is_last_line: bool = line_index == len(affected_lines) - 1
        is_single_line: bool = is_first_line and is_last_line
        if is_same_line:
            line_x0, line_x1 = sel_start_x, sel_end_x
        elif is_single_line:
            line_x0, line_x1 = sel_start_x, sel_end_x
        elif is_first_line:
            line_x0, line_x1 = sel_start_x, cell_x1
        elif is_last_line:
            line_x0, line_x1 = cell_x0, sel_end_x
        else:
            line_x0, line_x1 = cell_x0, cell_x1

        selected_chars: list[Character] = line.get_characters_in_x_range(
            line_x0, line_x1
        )
        if not selected_chars:
            continue

        selected_chars = [c for c in selected_chars if c.text not in BULLET_CHARS]
        while selected_chars and not selected_chars[0].text.strip():
            selected_chars = selected_chars[1:]
        while selected_chars and not selected_chars[-1].text.strip():
            selected_chars = selected_chars[:-1]
        if not selected_chars:
            continue

        span_x0: float = min(c.x0 for c in selected_chars)
        span_x1: float = max(c.x1 for c in selected_chars)
        span_y0: float = min(c.y0 for c in selected_chars)
        span_y1: float = max(c.y1 for c in selected_chars)

        span_text: str = "".join(c.text for c in selected_chars)
        if not span_text.strip():
            continue

        if not first_span_found:
            for char in selected_chars:
                if char.text.strip() and char.center_x >= first_line_start:
                    span_x0 = char.x0
                    break
            first_span_found = True

        span: SelectionSpan = SelectionSpan(
            text=span_text,
            x0=span_x0,
            y0=span_y0,
            x1=span_x1,
            y1=span_y1,
            line_index=line_index,
            span_index=0,
        )

        last_span = span
        spans.append(span)

    if last_span is not None and spans:
        last_line_idx = last_span.line_index
        if last_line_idx < len(affected_lines):
            last_line = affected_lines[last_line_idx]
            rightmost_x1 = last_span.x1
            for char in reversed(last_line.characters):
                if char.text.strip() and char.center_x <= last_line_end:
                    rightmost_x1 = char.x1
                    break

            spans[-1] = SelectionSpan(
                text=last_span.text,
                x0=last_span.x0,
                y0=last_span.y0,
                x1=rightmost_x1,
                y1=last_span.y1,
                line_index=last_span.line_index,
                span_index=last_span.span_index,
            )

    selection.set_range(
        SelectionRange(
            SelectionPoint(x=sel_start_x, y=sel_start_y),
            SelectionPoint(x=sel_end_x, y=sel_end_y),
            spans,
        )
    )


def raw_point_to_snapped_selection_point(
    local_x: float,
    local_y: float,
    page_index: int,
    file_path: str,
    scale: float,
) -> SelectionPoint:
    scale_adjusted_x: float = local_x / scale
    scale_adjusted_y: float = local_y / scale

    page_text: PageText | None = _get_page_text_for_point(
        file_path, page_index, scale_adjusted_x, scale_adjusted_y
    )
    line: TextLine | None = page_text.find_line_at_y(scale_adjusted_y) if page_text else None
    char: Character | None = line.find_character_at_x(scale_adjusted_x) if line else None

    if char and line:
        return SelectionPoint(x=char.center_x, y=line.center_y)
    elif line:
        return SelectionPoint(x=scale_adjusted_x, y=line.center_y)
    else:
        return SelectionPoint(x=scale_adjusted_x, y=scale_adjusted_y)


@lru_cache(maxsize=1)
def extract_page_text(file_path: str, page_index: int) -> PageText | None:
    def merge_and_sort(page_text: PageText, y_tolerance: float = 5.0) -> PageText:
        if not page_text.lines:
            return page_text

        lines_by_y = sorted(page_text.lines, key=lambda line: line.y_top)
        groups: list[list[TextLine]] = []

        for line in lines_by_y:
            placed = False
            for group in groups:
                if abs(line.y_top - group[0].y_top) <= y_tolerance:
                    group.append(line)
                    placed = True
                    break
            if not placed:
                groups.append([line])

        sorted_lines: list[TextLine] = []
        for group in groups:
            sorted_group = sorted(
                group,
                key=lambda line: line.characters[0].x0 if line.characters else 0,
            )
            sorted_lines.extend(sorted_group)

        return PageText(lines=sorted_lines)

    try:
        doc = fitz.open(file_path)
    except Exception:
        return None

    with doc:
        if page_index < 0 or page_index >= len(doc):
            return None
        page = doc[page_index]

        text_dict = page.get_text("rawdict")
        if not text_dict:
            return None

        text_lines: list[TextLine] = []

        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_chars: list[Character] = []
                for span in line.get("spans", []):
                    for char_data in span.get("chars", []):
                        char_bbox = char_data.get("bbox", (0, 0, 0, 0))
                        line_chars.append(
                            Character(
                                x0=float(char_bbox[0]),
                                y0=float(char_bbox[1]),
                                x1=float(char_bbox[2]),
                                y1=float(char_bbox[3]),
                                text=char_data.get("c", ""),
                            )
                        )

                if line_chars:
                    sorted_chars = sorted(line_chars, key=lambda c: c.x0)
                    text_lines.append(
                        TextLine(
                            y_top=min(c.y0 for c in sorted_chars),
                            y_bottom=max(c.y1 for c in sorted_chars),
                            characters=sorted_chars,
                        )
                    )

        if not text_lines:
            return None

        return merge_and_sort(PageText(lines=text_lines), y_tolerance=5.0)


@lru_cache(maxsize=1)
def extract_table_cells(file_path: str, page_index: int) -> list[CellBoundingBox]:
    try:
        doc = fitz.open(file_path)
    except Exception:
        return []

    with doc:
        if page_index < 0 or page_index >= len(doc):
            return []
        page = doc[page_index]
        finder = page.find_tables()
        cells: list[CellBoundingBox] = []
        for table in finder.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell is not None:
                        cells.append(
                            CellBoundingBox(
                                x0=float(cell[0]),
                                y0=float(cell[1]),
                                x1=float(cell[2]),
                                y1=float(cell[3]),
                            )
                        )
        return cells


def cell_containing_point(
    cells: list[CellBoundingBox], px: float, py: float
) -> CellBoundingBox | None:
    for cell in cells:
        if cell.x0 <= px <= cell.x1 and cell.y0 <= py <= cell.y1:
            return cell
    return None


def filter_page_text_to_cell(page_text: PageText, cell: CellBoundingBox) -> PageText:
    filtered_lines: list[TextLine] = []
    for line in page_text.lines:
        filtered_chars: list[Character] = [
            char
            for char in line.characters
            if cell.x0 <= (char.x0 + char.x1) / 2 <= cell.x1
            and cell.y0 <= (char.y0 + char.y1) / 2 <= cell.y1
        ]

        if filtered_chars:
            filtered_lines.append(
                TextLine(
                    y_top=min(c.y0 for c in filtered_chars),
                    y_bottom=max(c.y1 for c in filtered_chars),
                    characters=filtered_chars,
                )
            )

    return PageText(lines=filtered_lines)


def _get_page_text_for_point(
    file_path: str, page_index: int, scale_adjusted_x: float, scale_adjusted_y: float
) -> PageText | None:
    page_text: PageText | None = extract_page_text(file_path, page_index)
    if not page_text:
        return None

    anchor_cell: CellBoundingBox | None = cell_containing_point(
        extract_table_cells(file_path, page_index), scale_adjusted_x, scale_adjusted_y
    )
    if not anchor_cell:
        return page_text

    return filter_page_text_to_cell(page_text, anchor_cell)
