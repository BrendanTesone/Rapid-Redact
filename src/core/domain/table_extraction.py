"""
Table extraction utilities for AI detection.

Provides structured table detection and formatting for LLM analysis.
"""

from __future__ import annotations

from dataclasses import dataclass

import fitz


@dataclass
class TableStructure:
    """Structured representation of a table from a PDF page."""

    page_num: int
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1)
    title: str | None  # Text above table (if found)
    headers: list[str]  # First row if it looks like headers
    rows: list[list[str]]  # Remaining rows
    col_count: int
    row_count: int


def extract_tables_from_page(page: fitz.Page) -> list[TableStructure]:
    """Extract all tables from a PDF page using PyMuPDF find_tables() API.

    Filters out:
    - 1-column tables with <3 rows (likely formatted text, not true tables)
    - Tables with no content

    Args:
        page: PyMuPDF page object

    Returns:
        List of TableStructure objects representing detected tables
    """
    tables: list[TableStructure] = []
    finder = page.find_tables()

    for table in finder.tables:
        if table.col_count == 1 and table.row_count < 3:
            continue

        title = _find_table_title(page, table.bbox)
        headers: list[str] = []
        rows: list[list[str]] = []

        for r_idx, row in enumerate(table.rows):
            row_cells: list[str] = []
            for cell in row.cells:
                if cell is not None:
                    cell_rect = fitz.Rect(cell[0], cell[1], cell[2], cell[3])
                    cell_text = page.get_text("text", clip=cell_rect).strip()
                    row_cells.append(cell_text)
                else:
                    row_cells.append("")

            if r_idx == 0 and _looks_like_header_row(row_cells):
                headers = row_cells
            else:
                rows.append(row_cells)

        if not headers and not rows:
            continue

        tables.append(
            TableStructure(
                page_num=page.number,
                bbox=table.bbox,
                title=title,
                headers=headers,
                rows=rows,
                col_count=table.col_count,
                row_count=table.row_count,
            )
        )

    return tables


def _find_table_title(
    page: fitz.Page, table_bbox: tuple[float, float, float, float]
) -> str | None:
    """Find text immediately above a table that might be its title.

    Searches a region 100 points above the table and takes the last 1-2 lines.

    Args:
        page: PyMuPDF page object
        table_bbox: Table bounding box (x0, y0, x1, y1)

    Returns:
        Title text if found, None otherwise
    """
    x0, y0, x1, _ = table_bbox
    search_y0 = max(0, y0 - 100)
    search_rect = fitz.Rect(x0, search_y0, x1, y0)

    text_above = page.get_text("text", clip=search_rect).strip()
    if not text_above:
        return None

    lines = [line.strip() for line in text_above.split("\n") if line.strip()]
    if not lines:
        return None

    if len(lines[-1]) < 20 and len(lines) >= 2:
        title = " ".join(lines[-2:])
    else:
        title = lines[-1]

    title = _clean_title(title)
    return title if title else None


def _clean_title(title: str) -> str:
    """Remove common prefixes from table titles.

    Removes patterns like:
    - "Table 1:", "Table 1."
    - "Figure 2:", "Figure 2."
    - Numeric prefixes like "1.", "1.1."

    Args:
        title: Raw title text

    Returns:
        Cleaned title
    """
    import re

    title = re.sub(r"^(Table|Figure)\s+\d+[:.]\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^\d+(\.\d+)*[:.]\s*", "", title)
    return title.strip()


def _looks_like_header_row(row_cells: list[str]) -> bool:
    """Heuristic to determine if a row looks like table headers.

    Headers typically:
    - Are shorter (few words per cell)
    - Don't contain many numbers or special characters
    - Aren't all empty

    Args:
        row_cells: List of cell text values

    Returns:
        True if row likely contains headers, False otherwise
    """
    if not any(cell.strip() for cell in row_cells):
        return False

    long_cells = sum(1 for cell in row_cells if len(cell) > 50)
    if long_cells > len(row_cells) // 2:
        return False

    numeric_cells = sum(
        1
        for cell in row_cells
        if cell.strip() and cell.strip().replace(".", "").replace("%", "").isdigit()
    )
    if numeric_cells > len(row_cells) // 2:
        return False

    return True


def format_table_for_llm(table: TableStructure) -> str:
    """Format a table structure as LLM-friendly text.

    Format:
        [TABLE START: X columns x Y rows]
        [HEADER] col1 | col2 | col3
        [ROW] cell1 | cell2 | cell3
        [TABLE END]

    Empty cells are formatted as "-" for clarity.

    Args:
        table: TableStructure object

    Returns:
        Formatted table text
    """
    lines: list[str] = []

    if table.title:
        lines.append(table.title)
        lines.append("")

    lines.append(f"[TABLE START: {table.col_count} columns x {table.row_count} rows]")

    if table.headers:
        header_cells = [cell if cell.strip() else "-" for cell in table.headers]
        lines.append("[HEADER] " + " | ".join(header_cells))

    for row in table.rows:
        row_cells = [cell if cell.strip() else "-" for cell in row]
        while len(row_cells) < table.col_count:
            row_cells.append("-")
        lines.append("[ROW] " + " | ".join(row_cells))

    lines.append("[TABLE END]")

    return "\n".join(lines)


def get_table_region_text(
    page: fitz.Page, table_bbox: tuple[float, float, float, float]
) -> str:
    """Extract text within a table bounding box.

    Used for finding table titles or extracting table content.

    Args:
        page: PyMuPDF page object
        table_bbox: Table bounding box (x0, y0, x1, y1)

    Returns:
        Text within the table region
    """
    rect = fitz.Rect(table_bbox[0], table_bbox[1], table_bbox[2], table_bbox[3])
    return page.get_text("text", clip=rect).strip()
