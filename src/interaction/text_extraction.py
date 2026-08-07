"""Text extraction utilities for redaction mode."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

import fitz

from src.core.state.app_state import (
    TextLine as OldTextLine,
    TextSpan,
    TextStructure as OldTextStructure,
)
from src.core.state.selection_state import SelectionPoint
from src.interaction.refact_text_selection import (
    Character,
    cell_containing_point,
    extract_table_cells,
)

if TYPE_CHECKING:
    from src.interaction.text_selection_mode import (
        TextStructure as CharLevelTextStructure,
    )

BULLET_CHARS: frozenset[str] = frozenset(
    "•▪◦·–—-​‐"
)  # U+2022, U+25AA, U+25E6, U+00B7, U+2013, U+2014, U+002D, U+200B, U+2010


@dataclass(slots=True)
class SelectionSpan:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    line_index: int
    span_index: int


@dataclass(slots=True)
class Selection:
    spans: list[SelectionSpan]
    full_text: str


def _filter_lines_to_cell(
    line_chars: dict[tuple[int, int], list[Character]],
    line_bounds: dict[tuple[int, int], tuple[float, float]],
    cell: tuple[float, float, float, float],
) -> tuple[
    dict[tuple[int, int], list[Character]],
    dict[tuple[int, int], tuple[float, float]],
]:
    """Return line_chars and line_bounds restricted to lines overlapping cell.

    Uses center-based containment (same rule as selection logic): a character
    is inside the cell if its horizontal and vertical center falls within cell
    bounds. Recomputes line_bounds from filtered chars so y-extremes stay in-cell.
    """
    cx0, cy0, cx1, cy1 = cell
    filtered_chars: dict[tuple[int, int], list[Character]] = {}
    filtered_bounds: dict[tuple[int, int], tuple[float, float]] = {}
    for lk, chars in line_chars.items():
        cell_chars = [
            c
            for c in chars
            if cx0 <= (c.x0 + c.x1) / 2 <= cx1 and cy0 <= (c.y0 + c.y1) / 2 <= cy1
        ]
        if cell_chars:
            filtered_chars[lk] = cell_chars
            y0 = min(c.y0 for c in cell_chars)
            y1 = max(c.y1 for c in cell_chars)
            filtered_bounds[lk] = (y0, y1)
    return filtered_chars, filtered_bounds


def extract_text_structure(file_path: str, page_index: int) -> OldTextStructure | None:
    with fitz.open(file_path) as doc:
        if page_index < 0 or page_index >= len(doc):
            return None
        page = doc[page_index]
        text_dict = page.get_text("dict")

        lines: list[OldTextLine] = []
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_dir = line.get("dir", None)
                if line_dir:
                    if abs(line_dir[0]) < 0.9:
                        continue

                line_bbox = line.get("bbox", None)
                if line_bbox:
                    width = line_bbox[2] - line_bbox[0]
                    height = line_bbox[3] - line_bbox[1]
                    if height > width:
                        continue

                line_spans: list[TextSpan] = []
                for span in line.get("spans", []):
                    bbox = span.get("bbox", (0, 0, 0, 0))
                    line_spans.append(
                        TextSpan(
                            text=span.get("text", ""),
                            x0=bbox[0],
                            y0=bbox[1],
                            x1=bbox[2],
                            y1=bbox[3],
                        )
                    )
                if line_spans:
                    lines.append(OldTextLine(spans=line_spans))

        return OldTextStructure(lines=lines)


@lru_cache(maxsize=32)
def OLD_extract_and_group_words(file_path: str, page_index: int) -> (
    tuple[
        dict[tuple[int, int], list[Character]],
        dict[tuple[int, int], tuple[float, float]],
    ]
    | None
):
    from collections import defaultdict

    with fitz.open(file_path) as doc:
        if page_index < 0 or page_index >= len(doc):
            return None
        page = doc[page_index]

        text_dict = page.get_text("rawdict")
        if not text_dict:
            return None

        lines: dict[tuple[int, int], list[Character]] = defaultdict(list)
        line_bounds: dict[tuple[int, int], tuple[float, float]] = {}

        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            block_no = block.get("number", 0)
            for line_no, line in enumerate(block.get("lines", [])):
                line_key = (block_no, line_no)
                for span in line.get("spans", []):
                    chars = span.get("chars", [])
                    for char_data in chars:
                        char_bbox = char_data.get("bbox", (0, 0, 0, 0))
                        char_text = char_data.get("c", "")
                        char = Character(
                            x0=float(char_bbox[0]),
                            y0=float(char_bbox[1]),
                            x1=float(char_bbox[2]),
                            y1=float(char_bbox[3]),
                            text=char_text,
                        )
                        lines[line_key].append(char)

        for line_key, line_chars in lines.items():
            line_chars.sort(key=lambda c: c.x0)
            lines[line_key] = line_chars

            y0 = min(c.y0 for c in line_chars)
            y1 = max(c.y1 for c in line_chars)
            line_bounds[line_key] = (y0, y1)

        return (lines, line_bounds)


def snap_point_to_line_then_character(
    point: SelectionPoint,
    text_structure: CharLevelTextStructure,
) -> SelectionPoint:
    """Snap point to nearest line vertically, then nearest character horizontally.

    Tie-break uses horizontal distance to line's x-range to correctly handle
    multi-column tables. Snapped x is left edge if cursor left of center, right edge otherwise.
    """
    px, py = point.x, point.y
    line_chars = text_structure.line_chars
    line_bounds = text_structure.line_bounds

    if not line_chars:
        return SelectionPoint(x=px, y=py, snapped_char_idx=None, line_index=None)

    sorted_line_keys = sorted(line_bounds.keys(), key=lambda k: line_bounds[k][0])

    nearest_line_key: tuple[int, int] | None = None
    min_vert_dist = float("inf")
    min_horiz_dist_for_tie = float("inf")

    for lk in sorted_line_keys:
        ly0, ly1 = line_bounds[lk]
        if py < ly0:
            vdist = ly0 - py
        elif py > ly1:
            vdist = py - ly1
        else:
            vdist = 0.0

        chars_lk = line_chars.get(lk, [])
        if chars_lk:
            lx0 = min(c.x0 for c in chars_lk)
            lx1 = max(c.x1 for c in chars_lk)
            hdist_to_line = max(0.0, lx0 - px) if px < lx0 else max(0.0, px - lx1)
        else:
            hdist_to_line = float("inf")

        if vdist < min_vert_dist or (
            vdist == min_vert_dist and hdist_to_line < min_horiz_dist_for_tie
        ):
            min_vert_dist = vdist
            min_horiz_dist_for_tie = hdist_to_line
            nearest_line_key = lk

    if nearest_line_key is None:
        return SelectionPoint(x=px, y=py, snapped_char_idx=None, line_index=None)

    line_index = sorted_line_keys.index(nearest_line_key)
    chars = line_chars[nearest_line_key]
    if not chars:
        return SelectionPoint(x=px, y=py, snapped_char_idx=None, line_index=None)

    selectable = [
        (i, c)
        for i, c in enumerate(chars)
        if c.text not in BULLET_CHARS and c.text.strip() != ""
    ]
    candidates: list[tuple[int, Character]] = (
        selectable if selectable else list(enumerate(chars))
    )

    nearest_char_idx = candidates[0][0]
    nearest_char = candidates[0][1]
    min_horiz_dist = float("inf")
    for orig_idx, c in candidates:
        char_cx = (c.x0 + c.x1) / 2
        hdist = abs(px - char_cx)
        if hdist < min_horiz_dist:
            min_horiz_dist = hdist
            nearest_char_idx = orig_idx
            nearest_char = c

    char_cx = (nearest_char.x0 + nearest_char.x1) / 2
    char_mid_y = (nearest_char.y0 + nearest_char.y1) / 2

    snapped_x = nearest_char.x0 if px <= char_cx else nearest_char.x1

    return SelectionPoint(
        x=snapped_x,
        y=char_mid_y,
        snapped_char_idx=nearest_char_idx,
        line_index=line_index,
    )


def _create_selection_word_based(
    file_path: str,
    page_index: int,
    start_point: tuple[float, float],
    end_point: tuple[float, float],
) -> Selection | None:
    if not file_path or page_index is None:
        return None

    result = OLD_extract_and_group_words(file_path, page_index)
    if not result:
        return None

    lines, line_bounds = result

    start_x, start_y = start_point
    end_x, end_y = end_point

    orig_start_x, orig_start_y = start_x, start_y

    if end_y < start_y or (abs(end_y - start_y) < 5 and end_x < start_x):
        start_x, start_y, end_x, end_y = end_x, end_y, start_x, start_y

    table_cells = extract_table_cells(file_path, page_index)
    anchor_cell = cell_containing_point(table_cells, orig_start_x, orig_start_y)
    cell_x0: float = -float("inf")
    cell_x1: float = float("inf")
    if anchor_cell:
        ac_x0, ac_y0, ac_x1, ac_y1 = anchor_cell
        cell_x0, cell_x1 = ac_x0, ac_x1
        start_x = max(ac_x0, min(ac_x1, start_x))
        start_y = max(ac_y0, min(ac_y1, start_y))
        end_x = max(ac_x0, min(ac_x1, end_x))
        end_y = max(ac_y0, min(ac_y1, end_y))

    _TOL = 2.0 if start_y == end_y else 0.0
    affected_lines: list[tuple[tuple[int, int], float, float]] = []
    for line_key, (line_y0, line_y1) in line_bounds.items():
        line_center_y = (line_y0 + line_y1) / 2
        if start_y - _TOL <= line_center_y <= end_y + _TOL:
            affected_lines.append((line_key, line_y0, line_y1))

    if not affected_lines:
        return None

    affected_lines.sort(key=lambda item: item[1])

    spans: list[SelectionSpan] = []

    for idx, (line_key, line_y0, line_y1) in enumerate(affected_lines):
        line_chars = lines.get(line_key, [])
        if not line_chars:
            continue

        is_first_line = idx == 0
        is_last_line = idx == len(affected_lines) - 1
        is_single_line = is_first_line and is_last_line

        if is_single_line:
            sel_x0 = start_x
            sel_x1 = end_x
        elif is_first_line:
            sel_x0 = start_x
            sel_x1 = cell_x1
        elif is_last_line:
            sel_x0 = cell_x0
            sel_x1 = end_x
        else:
            sel_x0 = cell_x0
            sel_x1 = cell_x1

        selected_chars = []
        for c in line_chars:
            char_cx = (c.x0 + c.x1) / 2
            if char_cx >= sel_x0 and char_cx <= sel_x1:
                selected_chars.append(c)

        if not selected_chars:
            continue

        selected_chars = [c for c in selected_chars if c.text not in BULLET_CHARS]
        while selected_chars and selected_chars[0].text.strip() == "":
            selected_chars = selected_chars[1:]
        while selected_chars and selected_chars[-1].text.strip() == "":
            selected_chars = selected_chars[:-1]

        if not selected_chars:
            continue

        span_x0 = min(c.x0 for c in selected_chars)
        span_x1 = max(c.x1 for c in selected_chars)
        span_y0 = min(c.y0 for c in selected_chars)
        span_y1 = max(c.y1 for c in selected_chars)

        span_text = "".join(c.text for c in selected_chars)

        if not span_text.strip():
            continue

        span = SelectionSpan(
            x0=span_x0,
            y0=span_y0,
            x1=span_x1,
            y1=span_y1,
            text=span_text,
            line_index=idx,
            span_index=0,
        )
        spans.append(span)

    if not spans:
        return None

    full_text = " ".join(span.text for span in spans)
    return Selection(spans=spans, full_text=full_text)
