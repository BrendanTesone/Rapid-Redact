from __future__ import annotations

import uuid

import fitz

from src.core.state.app_state import RedactionBox, SelectionMode, TableRedactionBox
from src.controllers.amendment.Refactor.interpret_text_refactor import interpret_text


def _count_intersecting_cells(rect: fitz.Rect, table: fitz.table.Table) -> int:
    """Count how many cells the redaction rectangle intersects.

    Counts cells with >20% overlap. Uses table.rows[i].cells[j] to get actual cell bounding boxes.
    """
    if not hasattr(table, "rows") or not table.rows:
        return 0

    intersecting_count = 0

    for row_idx, row in enumerate(table.rows):
        if not hasattr(row, "cells"):
            continue

        cells = row.cells
        if not isinstance(cells, (list, tuple)):
            cells = [cells]

        for col_idx, cell_bbox in enumerate(cells):
            if isinstance(cell_bbox, fitz.Rect):
                cell_rect = cell_bbox
            elif isinstance(cell_bbox, (tuple, list)) and len(cell_bbox) >= 4:
                cell_rect = fitz.Rect(
                    cell_bbox[0], cell_bbox[1], cell_bbox[2], cell_bbox[3]
                )
            else:
                continue

            if rect.intersects(cell_rect):
                intersection_rect = rect & cell_rect
                intersection_area = intersection_rect.width * intersection_rect.height
                rect_area = rect.width * rect.height

                overlap_percentage = (
                    intersection_area / rect_area if rect_area > 0 else 0
                )

                if overlap_percentage > 0.20:
                    intersecting_count += 1

    return intersecting_count


def interpret_table(
    raw_box: RedactionBox, page: fitz.Page, page_idx: int
) -> list[RedactionBox]:
    rect = fitz.Rect(raw_box.x, raw_box.y, raw_box.x + raw_box.w, raw_box.y + raw_box.h)

    tables = page.find_tables()

    if not tables or not tables.tables:
        return []

    table_intersection = None
    matched_table = None

    for table in tables.tables:
        intersection = rect & table.bbox
        if not intersection.is_empty:
            table_intersection = intersection
            matched_table = table
            break

    if not table_intersection or matched_table is None:
        return []

    cell_count = _count_intersecting_cells(table_intersection, matched_table)

    if cell_count <= 1:
        return interpret_text(raw_box, page, page_idx)

    boxes: list[RedactionBox] = []

    table_data = matched_table.extract()
    row_count = len(table_data) if table_data else 0
    col_count = len(table_data[0]) if table_data and table_data[0] else 0

    table_bbox = matched_table.bbox
    if isinstance(table_bbox, tuple):
        bbox_for_title = table_bbox
    else:
        bbox_for_title = (table_bbox.x0, table_bbox.y0, table_bbox.x1, table_bbox.y1)

    adjacency_graph = _build_adjacency_graph(table_data)
    headers = _extract_headers(table_data)
    title = _extract_title(page, bbox_for_title)

    table_bbox = matched_table.bbox
    if isinstance(table_bbox, tuple):
        bbox_tuple = (
            float(table_bbox[0]),
            float(table_bbox[1]),
            float(table_bbox[2]),
            float(table_bbox[3]),
        )
    else:
        bbox_tuple = (
            float(table_bbox.x0),
            float(table_bbox.y0),
            float(table_bbox.x1),
            float(table_bbox.y1),
        )

    table_box = TableRedactionBox(
        id=str(uuid.uuid4()),
        x=float(table_intersection.x0),
        y=float(table_intersection.y0),
        w=float(table_intersection.x1 - table_intersection.x0),
        h=float(table_intersection.y1 - table_intersection.y0),
        page=page_idx + 1,
        selection_mode=SelectionMode.RECTANGLE,
        term="TABLE",
        match="",
        batch_id=None,
        adjacency_graph=adjacency_graph,
        headers=headers,
        title=title,
        row_count=row_count,
        col_count=col_count,
        table_bbox=bbox_tuple,
    )
    boxes.append(table_box)

    non_table_rects = _subtract_rect(rect, table_intersection)
    for non_table_rect in non_table_rects:
        if _has_text_content(page, non_table_rect):
            text_raw_box = RedactionBox(
                id=str(uuid.uuid4()),
                x=float(non_table_rect.x0),
                y=float(non_table_rect.y0),
                w=float(non_table_rect.x1 - non_table_rect.x0),
                h=float(non_table_rect.y1 - non_table_rect.y0),
                page=page_idx + 1,
                selection_mode=raw_box.selection_mode,
                term="raw",
                match="",
                batch_id=None,
            )
            text_boxes = interpret_text(text_raw_box, page, page_idx)
            boxes.extend(text_boxes)

    return boxes


def _subtract_rect(rect: fitz.Rect, intersection: fitz.Rect) -> list[fitz.Rect]:
    remainders = []

    remaining_top = intersection.y0 - rect.y0
    if remaining_top > 1:
        remainders.append(fitz.Rect(rect.x0, rect.y0, rect.x1, intersection.y0))

    remaining_bottom = rect.y1 - intersection.y1
    if remaining_bottom > 1:
        remainders.append(fitz.Rect(rect.x0, intersection.y1, rect.x1, rect.y1))

    remaining_left = intersection.x0 - rect.x0
    if remaining_left > 1:
        remainders.append(fitz.Rect(rect.x0, rect.y0, intersection.x0, rect.y1))

    remaining_right = rect.x1 - intersection.x1
    if remaining_right > 1:
        remainders.append(fitz.Rect(intersection.x1, rect.y0, rect.x1, rect.y1))

    return remainders


def _has_text_content(page: fitz.Page, rect: fitz.Rect) -> bool:
    text = page.get_text("text", clip=rect).strip()
    return bool(text)


def _build_adjacency_graph(
    table_data: list[list[str]],
) -> dict[tuple[int, int], dict[str, str | None]]:
    """Build adjacency graph for key table positions (corners and center).

    Used for matching tables across documents by comparing structural relationships
    between cells, not just content.
    """
    if not table_data or not table_data[0]:
        return {}

    visible_rows = len(table_data)
    visible_cols = len(table_data[0])

    key_positions = [
        (0, 0),
        (0, visible_cols - 1),
        (visible_rows - 1, 0),
        (visible_rows - 1, visible_cols - 1),
        (visible_rows // 2, visible_cols // 2),
    ]

    graph: dict[tuple[int, int], dict[str, str | None]] = {}

    for row_idx, col_idx in key_positions:
        if row_idx >= visible_rows or col_idx >= visible_cols:
            continue

        cell = table_data[row_idx][col_idx]
        cell_content = str(cell).strip() if cell is not None else ""

        def safe_cell(r: int, c: int) -> str | None:
            if r < 0 or r >= visible_rows or c < 0 or c >= visible_cols:
                return None
            val = table_data[r][c]
            return str(val).strip() if val is not None else ""

        graph[(row_idx, col_idx)] = {
            "content": cell_content,
            "up": safe_cell(row_idx - 1, col_idx),
            "down": safe_cell(row_idx + 1, col_idx),
            "left": safe_cell(row_idx, col_idx - 1),
            "right": safe_cell(row_idx, col_idx + 1),
        }

    return graph


def _extract_headers(table_data: list[list[str]]) -> list[str]:
    if not table_data:
        return []

    return [str(cell).strip() if cell is not None else "" for cell in table_data[0]]


def _extract_title(
    page: fitz.Page, table_bbox: tuple[float, float, float, float]
) -> str | None:
    """Extract table title from text above the table (within 50 points)."""
    search_rect = fitz.Rect(
        table_bbox[0], max(0, table_bbox[1] - 50), table_bbox[2], table_bbox[1]
    )

    text = page.get_text("text", clip=search_rect).strip()
    if not text:
        return None

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return str(lines[-1]) if lines else None
