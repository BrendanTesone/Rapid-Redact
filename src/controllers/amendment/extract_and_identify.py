"""
Extraction and identification logic for amendment redaction transfer.

Extracts redactions from source PDF and identifies their type (table/drawing/text).
"""

from __future__ import annotations

import fitz

from src.controllers.amendment.image_amendment import (
    CellReference,
    DrawingClusterRedaction,
    TableRedaction,
)

HAS_FITZ = True


class DrawingClusterDetector:
    """Detect redactions that overlap vector drawing clusters."""

    OVERLAP_THRESHOLD = 0.80
    NEARBY_RADIUS = 30.0

    def detect_drawing_overlaps(
        self, page: fitz.Page, redaction_rect: fitz.Rect
    ) -> DrawingClusterRedaction | None:
        """Check if redaction overlaps a drawing cluster.

        Returns DrawingClusterRedaction if overlap >= 80%, else None.
        Excludes redactions that overlap with tables.
        """
        if self._overlaps_table(page, redaction_rect):
            return None

        drawings = self._extract_drawings(page)
        if not drawings:
            return None

        overlapping = [
            d for d in drawings if (d["rect"] & redaction_rect).get_area() > 0
        ]

        if not overlapping:
            return None

        # Require at least 5 overlapping drawings to filter out borders/lines
        if len(overlapping) < 5:
            return None

        expanded_rect = fitz.Rect(
            redaction_rect.x0 - self.NEARBY_RADIUS,
            redaction_rect.y0 - self.NEARBY_RADIUS,
            redaction_rect.x1 + self.NEARBY_RADIUS,
            redaction_rect.y1 + self.NEARBY_RADIUS,
        )
        nearby = [d for d in drawings if (d["rect"] & expanded_rect).get_area() > 0]

        cluster_rect = self._union_drawings(nearby)
        if cluster_rect is None:
            return None

        overlap_pct = self._calculate_overlap(redaction_rect, cluster_rect)

        if overlap_pct < self.OVERLAP_THRESHOLD:
            return None

        rel_coords = self._normalize_coordinates(redaction_rect, cluster_rect)

        return DrawingClusterRedaction(
            page_num=page.number + 1,
            cluster_rect=(
                cluster_rect.x0,
                cluster_rect.y0,
                cluster_rect.x1,
                cluster_rect.y1,
            ),
            redaction_rect=(
                redaction_rect.x0,
                redaction_rect.y0,
                redaction_rect.x1,
                redaction_rect.y1,
            ),
            drawing_count=len(nearby),
            relative_x0=rel_coords[0],
            relative_y0=rel_coords[1],
            relative_x1=rel_coords[2],
            relative_y1=rel_coords[3],
            overlap_percentage=overlap_pct,
        )

    def _overlaps_table(self, page: fitz.Page, redaction_rect: fitz.Rect) -> bool:
        """Check if redaction overlaps with a table."""
        tables = page.find_tables()

        if not tables:
            return False

        for table in tables:
            table_rect = table.bbox
            intersection = redaction_rect & table_rect

            if not intersection.is_empty:
                intersection_area = intersection.width * intersection.height
                redaction_area = redaction_rect.width * redaction_rect.height

                if redaction_area > 0:
                    overlap_pct = intersection_area / redaction_area
                    # >= 30% overlap threshold to classify as table redaction
                    if overlap_pct >= 0.30:
                        return True

        return False

    def _calculate_text_coverage(
        self, page: fitz.Page, redaction_rect: fitz.Rect
    ) -> float:
        """Calculate what percentage of the redaction box is covered by text.

        Returns: Float [0.0-1.0] representing text coverage percentage
        """
        text_blocks = page.get_text("blocks")

        if not text_blocks:
            return 0.0

        total_text_area = 0.0
        redaction_area = redaction_rect.width * redaction_rect.height

        if redaction_area == 0:
            return 0.0

        for block in text_blocks:
            if len(block) < 4:
                continue

            block_rect = fitz.Rect(block[0], block[1], block[2], block[3])
            intersection = redaction_rect & block_rect

            if not intersection.is_empty:
                intersection_area = intersection.width * intersection.height
                total_text_area += intersection_area

        return float(min(1.0, total_text_area / redaction_area))

    def has_text_content(self, page: fitz.Page, redaction_rect: fitz.Rect) -> bool:
        """Check if redaction box contains any text."""
        text_coverage = self._calculate_text_coverage(page, redaction_rect)
        return text_coverage > 0.0

    def _extract_drawings(self, page: fitz.Page) -> list[dict[str, object]]:
        """Extract all vector drawings from page."""
        return page.get_drawings()  # type: ignore[no-any-return]

    def _union_drawings(self, drawings: list[dict[str, object]]) -> fitz.Rect | None:
        if not drawings:
            return None

        union_rect = None
        for drawing in drawings:
            rect = drawing["rect"]
            if union_rect is None:
                union_rect = rect
            else:
                union_rect |= rect  # type: ignore[operator]

        return union_rect

    def _calculate_overlap(
        self, redaction_rect: fitz.Rect, cluster_rect: fitz.Rect
    ) -> float:
        intersection = redaction_rect & cluster_rect
        if intersection.is_empty:
            return 0.0

        intersection_area = float(intersection.width * intersection.height)
        cluster_area = float(cluster_rect.width * cluster_rect.height)

        if cluster_area == 0:
            return 0.0

        return float(intersection_area / cluster_area)

    def _normalize_coordinates(
        self, redaction_rect: fitz.Rect, cluster_rect: fitz.Rect
    ) -> tuple[float, float, float, float]:
        """Convert redaction coords to [0.0-1.0] relative to cluster."""
        cluster_width = cluster_rect.width
        cluster_height = cluster_rect.height

        if cluster_width == 0 or cluster_height == 0:
            return (0.0, 0.0, 1.0, 1.0)

        relative_x0 = (redaction_rect.x0 - cluster_rect.x0) / cluster_width
        relative_y0 = (redaction_rect.y0 - cluster_rect.y0) / cluster_height
        relative_x1 = (redaction_rect.x1 - cluster_rect.x0) / cluster_width
        relative_y1 = (redaction_rect.y1 - cluster_rect.y0) / cluster_height

        relative_x0 = max(0.0, min(1.0, relative_x0))
        relative_y0 = max(0.0, min(1.0, relative_y0))
        relative_x1 = max(0.0, min(1.0, relative_x1))
        relative_y1 = max(0.0, min(1.0, relative_y1))

        return (relative_x0, relative_y0, relative_x1, relative_y1)


class TableDetector:
    """Detects table redactions and extracts metadata."""

    OVERLAP_THRESHOLD = 0.80

    def detect_table_overlap(
        self, page: fitz.Page, redaction_rect: fitz.Rect
    ) -> TableRedaction | None:
        """Check if redaction overlaps a table and extract metadata.

        Returns TableRedaction if overlap >= 80%, else None.
        """
        from src.core.domain.table_extraction import extract_tables_from_page

        table_structures = extract_tables_from_page(page)

        if not table_structures:
            return None

        best_overlap_pct = 0.0
        best_table_structure = None

        tables = page.find_tables()
        if not tables or not tables.tables:
            return None

        for table_struct, table_obj in zip(table_structures, tables.tables):
            table_rect = fitz.Rect(table_struct.bbox)
            intersection = redaction_rect & table_rect

            if not intersection.is_empty:
                intersection_area = intersection.width * intersection.height
                redaction_area = redaction_rect.width * redaction_rect.height

                if redaction_area > 0:
                    overlap_pct = intersection_area / redaction_area

                    if overlap_pct > best_overlap_pct:
                        best_overlap_pct = overlap_pct
                        best_table_structure = (table_struct, table_obj)

        if best_overlap_pct < self.OVERLAP_THRESHOLD:
            return None

        if best_table_structure is None:
            return None

        table_struct, table_obj = best_table_structure
        table_rect = fitz.Rect(table_struct.bbox)

        rel_coords = self._normalize_coordinates(redaction_rect, table_rect)

        top_left_cell = self._get_cell_bbox(table_obj, 0, 0)
        top_right_cell = self._get_cell_bbox(
            table_obj, 0, table_struct.col_count - 1
        )

        adjacency_graph = self._build_adjacency_graph(table_obj, page)

        redacted_cell_text = page.get_text("text", clip=redaction_rect).strip()

        print(
            f"    🔍 Found table with {len(table_obj.rows)} rows, bbox=({table_rect.x0:.1f}, {table_rect.y0:.1f}, {table_rect.x1:.1f}, {table_rect.y1:.1f})"
        )
        print(
            f"       Redaction: bbox=({redaction_rect.x0:.1f}, {redaction_rect.y0:.1f}, {redaction_rect.x1:.1f}, {redaction_rect.y1:.1f})"
        )

        center_cell_pos = self._find_containing_cell(table_obj, redaction_rect)

        center_cell_ref = None
        up_cell_ref = None
        down_cell_ref = None
        left_cell_ref = None
        right_cell_ref = None

        if center_cell_pos:
            center_row, center_col = center_cell_pos

            center_cell_ref = self._create_cell_reference(
                page, table_obj, center_row, center_col, redaction_rect
            )

            if center_row > 0:
                up_cell_ref = self._create_cell_reference(
                    page, table_obj, center_row - 1, center_col, redaction_rect
                )

            if center_row < len(table_obj.rows) - 1:
                down_cell_ref = self._create_cell_reference(
                    page, table_obj, center_row + 1, center_col, redaction_rect
                )

            if center_col > 0:
                left_cell_ref = self._create_cell_reference(
                    page, table_obj, center_row, center_col - 1, redaction_rect
                )

            if center_col < len(table_obj.rows[center_row].cells) - 1:
                right_cell_ref = self._create_cell_reference(
                    page, table_obj, center_row, center_col + 1, redaction_rect
                )

        return TableRedaction(
            page_num=page.number + 1,
            table_bbox=(
                table_rect.x0,
                table_rect.y0,
                table_rect.x1,
                table_rect.y1,
            ),
            redaction_bbox=(
                redaction_rect.x0,
                redaction_rect.y0,
                redaction_rect.x1,
                redaction_rect.y1,
            ),
            relative_x0=rel_coords[0],
            relative_y0=rel_coords[1],
            relative_x1=rel_coords[2],
            relative_y1=rel_coords[3],
            col_count=table_struct.col_count,
            row_count=table_struct.row_count,
            title=table_struct.title,
            headers=table_struct.headers,
            top_left_cell=top_left_cell,
            top_right_cell=top_right_cell,
            overlap_percentage=best_overlap_pct,
            redacted_cell_text=redacted_cell_text,
            adjacency_graph=adjacency_graph,
            center_cell=center_cell_ref,
            up_cell=up_cell_ref,
            down_cell=down_cell_ref,
            left_cell=left_cell_ref,
            right_cell=right_cell_ref,
        )

    def _build_adjacency_graph(
        self, table: fitz.table.Table, page: fitz.Page
    ) -> dict[tuple[int, int], dict[str, str | None]]:
        """Build adjacency graph from visible table fragment.

        Samples 5 key cells and records their neighbor relationships.
        Uses fragment-relative positions (not absolute table positions).
        """
        if not HAS_FITZ:
            return {}

        rows_data: list[list[str]] = []

        for row in table.rows:
            row_cells: list[str] = []
            for cell in row.cells:
                if cell is not None:
                    cell_rect = fitz.Rect(cell[0], cell[1], cell[2], cell[3])
                    cell_text = page.get_text("text", clip=cell_rect).strip()
                    row_cells.append(cell_text)
                else:
                    row_cells.append("")
            rows_data.append(row_cells)

        if not rows_data or not rows_data[0]:
            return {}

        visible_rows = len(rows_data)
        visible_cols = len(rows_data[0])

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

            cell_content = rows_data[row_idx][col_idx].strip()

            neighbors: dict[str, str | None] = {
                "content": cell_content,
                "up": (
                    rows_data[row_idx - 1][col_idx].strip() if row_idx > 0 else None
                ),
                "down": (
                    rows_data[row_idx + 1][col_idx].strip()
                    if row_idx < visible_rows - 1
                    else None
                ),
                "left": (
                    rows_data[row_idx][col_idx - 1].strip() if col_idx > 0 else None
                ),
                "right": (
                    rows_data[row_idx][col_idx + 1].strip()
                    if col_idx < visible_cols - 1
                    else None
                ),
            }

            graph[(row_idx, col_idx)] = neighbors

        return graph

    def _normalize_coordinates(
        self, redaction_rect: fitz.Rect, table_rect: fitz.Rect
    ) -> tuple[float, float, float, float]:
        table_width = table_rect.width
        table_height = table_rect.height

        if table_width == 0 or table_height == 0:
            return (0.0, 0.0, 0.0, 0.0)

        rel_x0 = (redaction_rect.x0 - table_rect.x0) / table_width
        rel_y0 = (redaction_rect.y0 - table_rect.y0) / table_height
        rel_x1 = (redaction_rect.x1 - table_rect.x0) / table_width
        rel_y1 = (redaction_rect.y1 - table_rect.y0) / table_height

        return (rel_x0, rel_y0, rel_x1, rel_y1)

    def _get_cell_bbox(
        self, table_obj: fitz.table.Table, row_idx: int, col_idx: int
    ) -> tuple[float, float, float, float] | None:
        if row_idx >= len(table_obj.rows):
            return None

        row = table_obj.rows[row_idx]
        if col_idx >= len(row.cells):
            return None

        cell = row.cells[col_idx]
        if cell is None:
            return None

        return (cell[0], cell[1], cell[2], cell[3])

    def _find_containing_cell(
        self, table: fitz.table.Table, redaction_rect: fitz.Rect
    ) -> tuple[int, int] | None:
        best_overlap = 0.0
        best_cell = None

        print(
            f"       🔎 Searching for containing cell in table with {len(table.rows)} rows"
        )
        print(
            f"          Redaction rect: ({redaction_rect.x0:.1f}, {redaction_rect.y0:.1f}, {redaction_rect.x1:.1f}, {redaction_rect.y1:.1f})"
        )

        cells_checked = 0
        none_cells = 0
        overlaps_found = 0

        for row_idx, row in enumerate(table.rows):
            for col_idx, cell in enumerate(row.cells):
                cells_checked += 1
                if cell is None:
                    none_cells += 1
                    continue

                cell_rect = fitz.Rect(cell[0], cell[1], cell[2], cell[3])
                intersection = redaction_rect & cell_rect

                if not intersection.is_empty:
                    overlaps_found += 1
                    overlap_area = intersection.width * intersection.height
                    if overlap_area > best_overlap:
                        best_overlap = overlap_area
                        best_cell = (row_idx, col_idx)

        print(
            f"          Checked {cells_checked} cells, {none_cells} were None, {overlaps_found} overlaps found"
        )
        if best_cell:
            print(
                f"          ✓ Best cell: row={best_cell[0]}, col={best_cell[1]}, overlap={best_overlap:.2f}"
            )
        else:
            print("          ❌ No containing cell found")

        return best_cell

    def _create_cell_reference(
        self,
        page: fitz.Page,
        table: fitz.table.Table,
        row: int,
        col: int,
        redaction_rect: fitz.Rect,
    ) -> CellReference | None:
        if row < 0 or row >= len(table.rows):
            return None

        row_obj = table.rows[row]
        if col < 0 or col >= len(row_obj.cells):
            return None

        cell = row_obj.cells[col]
        if cell is None:
            return None

        cell_bbox = (cell[0], cell[1], cell[2], cell[3])
        cell_rect = fitz.Rect(cell_bbox)
        cell_text = page.get_text("text", clip=cell_rect).strip()

        offset_x = redaction_rect.x0 - cell_bbox[0]
        offset_y = redaction_rect.y0 - cell_bbox[1]

        return CellReference(
            row=row,
            col=col,
            cell_bbox=cell_bbox,
            cell_text=cell_text,
            offset_x=offset_x,
            offset_y=offset_y,
        )
