"""
Matching and placement logic for amendment redaction transfer.

Matches extracted redactions to destination PDF and calculates placement coordinates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import fitz

try:
    from rapidfuzz import fuzz

    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    fuzz = None  # type: ignore[assignment]

from src.controllers.amendment.image_amendment import (
    CellMatch,
    DrawingClusterInfo,
    DrawingClusterMatchScore,
    DrawingClusterRedaction,
    TableMatchScore,
    TableRedaction,
)

from src.controllers.amendment.extract_and_identify import (
    DrawingClusterDetector,
)

if TYPE_CHECKING:
    from src.core.domain.table_extraction import TableStructure


class DrawingClusterMatcher:
    """Match drawing clusters between source and target PDFs using multi-factor scoring."""

    DIMENSION_WEIGHT = 0.3
    ASPECT_WEIGHT = 0.2
    POSITION_WEIGHT = 0.3
    COUNT_WEIGHT = 0.2

    MIN_MATCH_SCORE = 0.65
    NEARBY_RADIUS = 30.0

    def find_best_match(
        self,
        target_doc: fitz.Document,
        source_cluster: DrawingClusterInfo,
        search_range_pages: int = 10,
    ) -> DrawingClusterMatchScore | None:
        """Find best matching drawing cluster in target PDF.

        Searches ±search_range_pages from source page. Requires 50% minimum score on
        all individual factors (dimension, aspect, position, count) and no table overlap.
        """
        detector = DrawingClusterDetector()
        all_candidates: list[DrawingClusterMatchScore] = []

        source_page_idx = source_cluster.page_num - 1

        for offset in range(-search_range_pages, search_range_pages + 1):
            target_page_idx = source_page_idx + offset

            if target_page_idx < 0 or target_page_idx >= len(target_doc):
                continue

            target_page = target_doc[target_page_idx]
            target_clusters = self._extract_page_clusters(target_page, detector)

            for target_cluster in target_clusters:
                score = self._score_match(source_cluster, target_cluster)

                print(
                    f"         [Page {target_cluster.page_num}] Cluster with {target_cluster.drawing_count} drawings: "
                    f"Total={score.total_score:.2f}, "
                    f"Dim={score.dimension_score:.2f}, "
                    f"Asp={score.aspect_score:.2f}, "
                    f"Pos={score.position_score:.2f}, "
                    f"Count={score.count_score:.2f}"
                )

                meets_criteria = (
                    score.total_score >= self.MIN_MATCH_SCORE
                    and score.dimension_score >= 0.50
                    and score.aspect_score >= 0.50
                    and score.position_score >= 0.50
                    and score.count_score >= 0.50
                )

                if meets_criteria:
                    all_candidates.append(score)
                    print("            ✓ Meets all criteria (≥0.50 on each factor)")
                else:
                    failures = []
                    if score.total_score < self.MIN_MATCH_SCORE:
                        failures.append(f"Total<{self.MIN_MATCH_SCORE}")
                    if score.dimension_score < 0.50:
                        failures.append("Dim<0.50")
                    if score.aspect_score < 0.50:
                        failures.append("Asp<0.50")
                    if score.position_score < 0.50:
                        failures.append("Pos<0.50")
                    if score.count_score < 0.50:
                        failures.append("Count<0.50")
                    print(f"            ✗ Failed: {', '.join(failures)}")

        if all_candidates:
            print(f"    📊 Found {len(all_candidates)} potential match(es):")

            sorted_candidates = sorted(
                all_candidates, key=lambda x: x.total_score, reverse=True
            )

            for i, candidate in enumerate(sorted_candidates, 1):
                print(
                    f"       [{i}] Page {candidate.cluster_info.page_num}: "
                    f"Total={candidate.total_score:.2f}, "
                    f"Dim={candidate.dimension_score:.2f}, "
                    f"Asp={candidate.aspect_score:.2f}, "
                    f"Pos={candidate.position_score:.2f}, "
                    f"Count={candidate.count_score:.2f}"
                )

            print("    🔍 Checking table overlap for top candidates...")
            for i, candidate in enumerate(sorted_candidates, 1):
                cluster_rect = candidate.cluster_info.fitz_rect
                candidate_page_idx = candidate.cluster_info.page_num - 1
                candidate_page = target_doc[candidate_page_idx]

                if detector._overlaps_table(candidate_page, cluster_rect):
                    print(
                        f"       [{i}] Page {candidate.cluster_info.page_num}: ✗ Overlaps table, skipping"
                    )
                    continue
                else:
                    print(
                        f"       [{i}] Page {candidate.cluster_info.page_num}: ✓ No table overlap"
                    )
                    print(
                        f"    ✓ Selected best match: Page {candidate.cluster_info.page_num} (score: {candidate.total_score:.2f})"
                    )
                    return candidate

            print("    ❌ All candidates overlap tables, no valid match")
            return None
        else:
            print("    ❌ No valid matches found (no clusters met all criteria)")
            return None

    def _extract_page_clusters(
        self, page: fitz.Page, detector: DrawingClusterDetector
    ) -> list[DrawingClusterInfo]:
        """Extract all drawing clusters using union-find algorithm.

        Groups all drawings within NEARBY_RADIUS using deterministic clustering.
        """
        drawings = detector._extract_drawings(page)
        page_num = page.number + 1

        if not drawings:
            print(f"         [Page {page_num}] No drawings found")
            return []

        parent = {id(d): id(d) for d in drawings}

        def find(x: int) -> int:
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        RADIUS = detector.NEARBY_RADIUS
        for i, d1 in enumerate(drawings):
            r1 = d1["rect"]
            expanded = fitz.Rect(
                r1.x0 - RADIUS,  # type: ignore[attr-defined]
                r1.y0 - RADIUS,  # type: ignore[attr-defined]
                r1.x1 + RADIUS,  # type: ignore[attr-defined]
                r1.y1 + RADIUS,  # type: ignore[attr-defined]
            )
            for d2 in drawings[i + 1 :]:
                r2 = d2["rect"]
                if (expanded & r2).get_area() > 0:
                    union(id(d1), id(d2))

        clusters: dict[int, list[dict[str, object]]] = {}
        for d in drawings:
            root = find(id(d))
            if root not in clusters:
                clusters[root] = []
            clusters[root].append(d)

        result = []
        for cluster_drawings in clusters.values():
            union_rect = detector._union_drawings(cluster_drawings)
            if union_rect is None:
                continue

            result.append(
                DrawingClusterInfo(
                    rect=(
                        union_rect.x0,
                        union_rect.y0,
                        union_rect.x1,
                        union_rect.y1,
                    ),
                    drawing_count=len(cluster_drawings),
                    page_num=page_num,
                )
            )

        if result:
            print(
                f"         [Page {page_num}] Found {len(result)} cluster(s) from {len(drawings)} total drawings"
            )
        else:
            print(
                f"         [Page {page_num}] {len(drawings)} drawings but no clusters formed"
            )

        return result

    def _score_match(
        self, source: DrawingClusterInfo, target: DrawingClusterInfo
    ) -> DrawingClusterMatchScore:
        """Calculate weighted multi-factor match score."""
        dim_score = self._dimension_similarity(source, target)
        asp_score = self._aspect_similarity(source, target)
        pos_score = self._position_similarity(source, target)
        count_score = self._count_similarity(source, target)

        total = (
            self.DIMENSION_WEIGHT * dim_score
            + self.ASPECT_WEIGHT * asp_score
            + self.POSITION_WEIGHT * pos_score
            + self.COUNT_WEIGHT * count_score
        )

        return DrawingClusterMatchScore(
            cluster_info=target,
            dimension_score=dim_score,
            aspect_score=asp_score,
            position_score=pos_score,
            count_score=count_score,
            total_score=total,
        )

    def _dimension_similarity(
        self, source: DrawingClusterInfo, target: DrawingClusterInfo
    ) -> float:
        source_w = source.rect[2] - source.rect[0]
        source_h = source.rect[3] - source.rect[1]
        target_w = target.rect[2] - target.rect[0]
        target_h = target.rect[3] - target.rect[1]

        if source_w == 0 or source_h == 0:
            return 0.0

        width_diff = abs(source_w - target_w) / max(source_w, target_w)
        height_diff = abs(source_h - target_h) / max(source_h, target_h)

        avg_similarity = 1.0 - ((width_diff + height_diff) / 2.0)
        return float(max(0.0, min(1.0, avg_similarity)))

    def _aspect_similarity(
        self, source: DrawingClusterInfo, target: DrawingClusterInfo
    ) -> float:
        source_aspect = source.aspect_ratio
        target_aspect = target.aspect_ratio

        if source_aspect == 0 or target_aspect == 0:
            return 0.0

        aspect_diff = abs(source_aspect - target_aspect) / max(
            source_aspect, target_aspect
        )
        return max(0.0, min(1.0, 1.0 - aspect_diff))

    def _position_similarity(
        self, source: DrawingClusterInfo, target: DrawingClusterInfo
    ) -> float:
        PAGE_WIDTH = 595.0
        PAGE_HEIGHT = 842.0

        source_x = source.rect[0] / PAGE_WIDTH
        source_y = source.rect[1] / PAGE_HEIGHT
        target_x = target.rect[0] / PAGE_WIDTH
        target_y = target.rect[1] / PAGE_HEIGHT

        x_diff = abs(source_x - target_x)
        y_diff = abs(source_y - target_y)
        distance = (x_diff + y_diff) / 2.0

        return float(max(0.0, min(1.0, 1.0 - distance)))

    def _count_similarity(
        self, source: DrawingClusterInfo, target: DrawingClusterInfo
    ) -> float:
        if source.drawing_count == 0 or target.drawing_count == 0:
            return 0.0

        count_diff = abs(source.drawing_count - target.drawing_count) / max(
            source.drawing_count, target.drawing_count
        )
        return float(max(0.0, min(1.0, 1.0 - count_diff)))


class DrawingClusterTransferer:
    """Reconstruct redactions on matched drawing clusters by aligning positions."""

    def reconstruct_redaction(
        self,
        cluster_redaction: DrawingClusterRedaction,
        target_cluster: DrawingClusterInfo,
    ) -> fitz.Rect:
        """Reconstruct redaction rectangle to cover the entire matched cluster.

        Returns full bounds of the matched drawing cluster, covering all drawings.
        """
        return target_cluster.fitz_rect


class CellContentMatcher:
    """Match table redactions by finding cells with similar content."""

    FUZZY_THRESHOLD = 0.85

    def find_matching_cell(
        self,
        dest_page: fitz.Page,
        source_redacted_text: str,
    ) -> tuple[float, float, float, float] | None:
        if not source_redacted_text:
            return None

        tables = dest_page.find_tables()
        if not tables or not tables.tables:
            return None

        for table in tables.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell is None:
                        continue

                    cell_rect = fitz.Rect(cell[0], cell[1], cell[2], cell[3])
                    cell_text = dest_page.get_text("text", clip=cell_rect).strip()

                    similarity = self._fuzzy_match(source_redacted_text, cell_text)

                    if similarity >= self.FUZZY_THRESHOLD:
                        print(
                            f"         🎯 Content match found (similarity={similarity:.2f})"
                        )
                        print(f"            Source: '{source_redacted_text[:40]}...'")
                        print(f"            Dest: '{cell_text[:40]}...'")
                        return (cell[0], cell[1], cell[2], cell[3])

        return None

    def _fuzzy_match(self, text1: str, text2: str) -> float:
        if not text1 or not text2:
            return 0.0

        t1 = text1.strip().lower()
        t2 = text2.strip().lower()

        if t1 == t2:
            return 1.0

        if HAS_RAPIDFUZZ and fuzz is not None:
            return float(fuzz.ratio(t1, t2) / 100.0)

        if t1 in t2 or t2 in t1:
            return 0.9

        return 0.0


class AdjacencyCellMatcher:
    """Match cells using center content + all 4 neighbors."""

    FUZZY_THRESHOLD = 0.70
    CENTER_WEIGHT = 5.0
    NEIGHBOR_WEIGHT = 1.0

    def find_best_matching_cell(
        self,
        dest_doc: fitz.Document,
        source: TableRedaction,
        page_offset: int = 0,
    ) -> CellMatch | None:
        """Find best matching cell in specified page range.

        Scores each cell by center content (weight=5) + 4 neighbors (weight=1 each).
        """
        if source.center_cell is None:
            return None

        best_match: CellMatch | None = None
        best_score = 0.0

        source_page = source.page_num - 1

        if page_offset >= 0:
            search_start = source_page
            search_end = min(len(dest_doc), source_page + page_offset + 1)
        else:
            search_start = max(0, source_page + page_offset)
            search_end = source_page + 1

        for page_idx in range(search_start, search_end):
            page = dest_doc[page_idx]
            tables = page.find_tables()

            if not tables or not tables.tables:
                continue

            for table_idx, table in enumerate(tables.tables):
                for row_idx, row in enumerate(table.rows):
                    for col_idx, cell in enumerate(row.cells):
                        if cell is None:
                            continue

                        match = self._score_cell(
                            page, table, row_idx, col_idx, page_idx, table_idx, source
                        )

                        if match and match.total_score > best_score:
                            best_match = match
                            best_score = match.total_score

                            if best_score >= 8.0:
                                return best_match

        if best_match and best_match.total_score >= (
            self.CENTER_WEIGHT * self.FUZZY_THRESHOLD
        ):
            return best_match

        return None

    def _score_cell(
        self,
        page: fitz.Page,
        table: fitz.table.Table,
        row: int,
        col: int,
        page_idx: int,
        table_idx: int,
        source: TableRedaction,
    ) -> CellMatch | None:
        if source.center_cell is None:
            return None

        cell = table.rows[row].cells[col]
        cell_bbox = (cell[0], cell[1], cell[2], cell[3])
        cell_text = page.get_text("text", clip=fitz.Rect(cell_bbox)).strip()

        center_score = (
            self._fuzzy_match(source.center_cell.cell_text, cell_text)
            * self.CENTER_WEIGHT
        )

        up_score = 0.0
        up_bbox = None
        if source.up_cell and row > 0:
            up_cell = table.rows[row - 1].cells[col]
            if up_cell:
                up_bbox = (up_cell[0], up_cell[1], up_cell[2], up_cell[3])
                up_text = page.get_text("text", clip=fitz.Rect(up_bbox)).strip()
                up_score = (
                    self._fuzzy_match(source.up_cell.cell_text, up_text)
                    * self.NEIGHBOR_WEIGHT
                )

        down_score = 0.0
        down_bbox = None
        if source.down_cell and row < len(table.rows) - 1:
            down_cell = table.rows[row + 1].cells[col]
            if down_cell:
                down_bbox = (down_cell[0], down_cell[1], down_cell[2], down_cell[3])
                down_text = page.get_text("text", clip=fitz.Rect(down_bbox)).strip()
                down_score = (
                    self._fuzzy_match(source.down_cell.cell_text, down_text)
                    * self.NEIGHBOR_WEIGHT
                )

        left_score = 0.0
        left_bbox = None
        if source.left_cell and col > 0:
            left_cell = table.rows[row].cells[col - 1]
            if left_cell:
                left_bbox = (left_cell[0], left_cell[1], left_cell[2], left_cell[3])
                left_text = page.get_text("text", clip=fitz.Rect(left_bbox)).strip()
                left_score = (
                    self._fuzzy_match(source.left_cell.cell_text, left_text)
                    * self.NEIGHBOR_WEIGHT
                )

        right_score = 0.0
        right_bbox = None
        if source.right_cell and col < len(table.rows[row].cells) - 1:
            right_cell = table.rows[row].cells[col + 1]
            if right_cell:
                right_bbox = (
                    right_cell[0],
                    right_cell[1],
                    right_cell[2],
                    right_cell[3],
                )
                right_text = page.get_text("text", clip=fitz.Rect(right_bbox)).strip()
                right_score = (
                    self._fuzzy_match(source.right_cell.cell_text, right_text)
                    * self.NEIGHBOR_WEIGHT
                )

        total_score = center_score + up_score + down_score + left_score + right_score

        return CellMatch(
            page_idx=page_idx,
            table_idx=table_idx,
            row_idx=row,
            col_idx=col,
            cell_bbox=cell_bbox,
            center_score=center_score,
            up_score=up_score,
            down_score=down_score,
            left_score=left_score,
            right_score=right_score,
            total_score=total_score,
            up_bbox=up_bbox,
            down_bbox=down_bbox,
            left_bbox=left_bbox,
            right_bbox=right_bbox,
        )

    def _fuzzy_match(self, text1: str, text2: str) -> float:
        """Fuzzy match two strings with multi-line and substring support.

        Matching strategy (in order):
        1. Exact match → 1.0
        2. Substring match → 0.95
        3. Token overlap for multi-word cells → 0.75-1.0 (requires 50% overlap)
        4. Partial/full fuzzy match via RapidFuzz → 0.0-1.0
        """
        if not text1 or not text2:
            return 0.0

        t1 = " ".join(text1.strip().lower().split())
        t2 = " ".join(text2.strip().lower().split())

        if t1 == t2:
            return 1.0

        if t1 in t2 or t2 in t1:
            return 0.95

        tokens1 = set(t1.split())
        tokens2 = set(t2.split())

        if len(tokens1) >= 3 or len(tokens2) >= 3:
            if tokens1 and tokens2:
                overlap = len(tokens1 & tokens2)
                max_tokens = max(len(tokens1), len(tokens2))
                token_ratio = overlap / max_tokens

                if token_ratio >= 0.5:
                    return min(1.0, 0.5 + (token_ratio * 0.5))

        if HAS_RAPIDFUZZ and fuzz:
            partial_score = float(fuzz.partial_ratio(t1, t2) / 100.0)

            if partial_score >= 0.85:
                return partial_score

            ratio_score = float(fuzz.ratio(t1, t2) / 100.0)
            return max(partial_score, ratio_score)

        return 0.0


class RelativePositionReconstructor:
    """Reconstruct redaction position using multiple reference cells."""

    def reconstruct_position(
        self,
        source: TableRedaction,
        match: CellMatch,
    ) -> tuple[float, float, float, float]:
        """Reconstruct redaction bbox using weighted average of cell-relative positions.

        Triangulates position from center cell (weight=5) + available neighbors (weight=1 each).
        """
        if source.center_cell is None:
            return match.cell_bbox

        original_w = source.redaction_bbox[2] - source.redaction_bbox[0]
        original_h = source.redaction_bbox[3] - source.redaction_bbox[1]

        estimates: list[tuple[float, float, float]] = []

        center_x0 = match.cell_bbox[0] + source.center_cell.offset_x
        center_y0 = match.cell_bbox[1] + source.center_cell.offset_y
        estimates.append((center_x0, center_y0, 5.0))

        print("    📍 CENTER cell reconstruction:")
        print(f"       Source cell bbox: {source.center_cell.cell_bbox}")
        print(
            f"       Source offset: ({source.center_cell.offset_x:.2f}, {source.center_cell.offset_y:.2f})"
        )
        print(f"       Dest cell bbox: {match.cell_bbox}")
        print(
            f"       Reconstructed x0: {match.cell_bbox[0]:.2f} + {source.center_cell.offset_x:.2f} = {center_x0:.2f}"
        )
        print(
            f"       Reconstructed y0: {match.cell_bbox[1]:.2f} + {source.center_cell.offset_y:.2f} = {center_y0:.2f}"
        )

        if source.up_cell and match.up_bbox:
            up_x0 = match.up_bbox[0] + source.up_cell.offset_x
            up_y0 = match.up_bbox[1] + source.up_cell.offset_y
            estimates.append((up_x0, up_y0, 1.0))

        if source.down_cell and match.down_bbox:
            down_x0 = match.down_bbox[0] + source.down_cell.offset_x
            down_y0 = match.down_bbox[1] + source.down_cell.offset_y
            estimates.append((down_x0, down_y0, 1.0))

        if source.left_cell and match.left_bbox:
            left_x0 = match.left_bbox[0] + source.left_cell.offset_x
            left_y0 = match.left_bbox[1] + source.left_cell.offset_y
            estimates.append((left_x0, left_y0, 1.0))
            print(
                f"    📍 LEFT cell: dest_bbox={match.left_bbox}, offset=({source.left_cell.offset_x:.2f}, {source.left_cell.offset_y:.2f}) → ({left_x0:.2f}, {left_y0:.2f})"
            )

        if source.right_cell and match.right_bbox:
            right_x0 = match.right_bbox[0] + source.right_cell.offset_x
            right_y0 = match.right_bbox[1] + source.right_cell.offset_y
            estimates.append((right_x0, right_y0, 1.0))
            print(
                f"    📍 RIGHT cell: dest_bbox={match.right_bbox}, offset=({source.right_cell.offset_x:.2f}, {source.right_cell.offset_y:.2f}) → ({right_x0:.2f}, {right_y0:.2f})"
            )

        total_weight = sum(w for _, _, w in estimates)
        avg_x0 = sum(x * w for x, _, w in estimates) / total_weight
        avg_y0 = sum(y * w for _, y, w in estimates) / total_weight

        print(
            f"    📐 Reconstructed position: ({avg_x0:.2f}, {avg_y0:.2f}) from {len(estimates)} estimates"
        )
        for i, (x, y, w) in enumerate(estimates):
            print(f"       Estimate {i+1}: ({x:.2f}, {y:.2f}) weight={w}")

        return (avg_x0, avg_y0, avg_x0 + original_w, avg_y0 + original_h)


class TableMatcher:
    """Matches tables between source and destination PDFs."""

    ADJACENCY_WEIGHT = 0.50
    STRUCTURE_WEIGHT = 0.25
    HEADER_WEIGHT = 0.15
    TITLE_WEIGHT = 0.10
    POSITION_WEIGHT = 0.0

    MATCH_THRESHOLD = 0.65

    def find_best_match(
        self, dest_page: fitz.Page, source_table: TableRedaction
    ) -> TableMatchScore | None:
        from src.core.domain.table_extraction import extract_tables_from_page

        table_structures = extract_tables_from_page(dest_page)

        if not table_structures:
            return None

        tables = dest_page.find_tables()
        if not tables or not tables.tables:
            return None

        best_score: TableMatchScore | None = None

        print(f"         Found {len(table_structures)} table(s) in destination page")
        print(f"         Source table: {source_table.row_count}x{source_table.col_count}")

        for idx, (table_struct, table_obj) in enumerate(
            zip(table_structures, tables.tables)
        ):
            structure_score = self._score_structure(source_table, table_struct)
            header_score = self._score_headers(source_table, table_struct)
            title_score = self._score_title(source_table, table_struct)
            position_score = self._score_position(source_table, table_struct)

            adjacency_score = self._score_adjacency_graph(
                source_table.adjacency_graph, table_struct
            )

            total_score = (
                adjacency_score * self.ADJACENCY_WEIGHT
                + structure_score * self.STRUCTURE_WEIGHT
                + header_score * self.HEADER_WEIGHT
                + title_score * self.TITLE_WEIGHT
                + position_score * self.POSITION_WEIGHT
            )

            match_score = TableMatchScore(
                table_idx=idx,
                structure_score=structure_score,
                header_score=header_score,
                title_score=title_score,
                position_score=position_score,
                adjacency_score=adjacency_score,
                total_score=total_score,
                table=table_obj,
            )

            print(
                f"         Table {idx}: {table_struct.row_count}x{table_struct.col_count} "
                f"→ score={total_score:.2f} (adj={adjacency_score:.2f}, struct={structure_score:.2f}, "
                f"hdr={header_score:.2f}, title={title_score:.2f}, pos={position_score:.2f})"
            )

            if best_score is None or total_score > best_score.total_score:
                best_score = match_score

        if best_score and best_score.total_score >= self.MATCH_THRESHOLD:
            return best_score

        if best_score:
            print(
                f"         Best match score {best_score.total_score:.2f} below threshold {self.MATCH_THRESHOLD}"
            )

        return None

    def _score_structure(
        self, source: TableRedaction, dest_table: TableStructure
    ) -> float:
        """Score structure similarity using gradient scale.

        Tolerates up to 5 rows/columns difference (common in amendments).
        """
        if (
            source.col_count == dest_table.col_count
            and source.row_count == dest_table.row_count
        ):
            return 1.0

        col_diff = abs(source.col_count - dest_table.col_count)
        row_diff = abs(source.row_count - dest_table.row_count)

        max_diff = 5

        col_score = max(0.0, 1.0 - (col_diff / max_diff))
        row_score = max(0.0, 1.0 - (row_diff / max_diff))

        return (col_score + row_score) / 2.0

    def _score_headers(
        self, source: TableRedaction, dest_table: TableStructure
    ) -> float:
        if not source.headers or not dest_table.headers:
            return 1.0

        try:
            from rapidfuzz import fuzz

            total_similarity = 0.0
            comparisons = min(len(source.headers), len(dest_table.headers))

            for i in range(comparisons):
                source_header = source.headers[i].strip()
                dest_header = dest_table.headers[i].strip()

                if not source_header and not dest_header:
                    total_similarity += 1.0
                elif not source_header or not dest_header:
                    total_similarity += 0.0
                else:
                    similarity_score: float = (
                        float(fuzz.ratio(source_header, dest_header)) / 100.0
                    )
                    total_similarity += similarity_score

            return total_similarity / comparisons if comparisons > 0 else 0.0

        except ImportError:
            matches = sum(
                1
                for i in range(min(len(source.headers), len(dest_table.headers)))
                if source.headers[i].strip() == dest_table.headers[i].strip()
            )
            total = min(len(source.headers), len(dest_table.headers))
            return matches / total if total > 0 else 0.0

    def _score_title(self, source: TableRedaction, dest_table: TableStructure) -> float:
        if not source.title and not dest_table.title:
            return 1.0

        if not source.title or not dest_table.title:
            return 0.5

        try:
            from rapidfuzz import fuzz  # noqa: PGH003

            ratio_result = fuzz.ratio(source.title, dest_table.title)
            similarity: float = float(ratio_result) / 100.0
            return similarity

        except ImportError:
            return 1.0 if source.title == dest_table.title else 0.0

    def _score_position(
        self, source: TableRedaction, dest_table: TableStructure
    ) -> float:
        PAGE_WIDTH = 595.0
        PAGE_HEIGHT = 842.0

        source_x = source.table_bbox[0] / PAGE_WIDTH
        source_y = source.table_bbox[1] / PAGE_HEIGHT
        dest_x = dest_table.bbox[0] / PAGE_WIDTH
        dest_y = dest_table.bbox[1] / PAGE_HEIGHT

        x_diff = abs(source_x - dest_x)
        y_diff = abs(source_y - dest_y)
        distance = (x_diff + y_diff) / 2.0

        return max(0.0, min(1.0, 1.0 - distance))

    def _score_adjacency_graph(
        self,
        source_graph: dict[tuple[int, int], dict[str, str | None]],
        dest_table: TableStructure,
    ) -> float:
        """Score similarity of cell adjacency graphs.

        Compares cell content (50% weight) and neighbor relationships (50% weight).
        Allows for table structure changes by searching alternate positions.
        """
        if not source_graph:
            print("         ⚠️  DEBUG: Source graph is empty")
            return 0.0

        dest_graph = self._build_dest_adjacency_graph(dest_table)
        if not dest_graph:
            print("         ⚠️  DEBUG: Dest graph is empty")
            return 0.0

        print(f"         🔍 DEBUG: Source graph has {len(source_graph)} cells")
        for pos, cell_data in list(source_graph.items())[:2]:
            content = cell_data.get("content") or ""
            content = content[:20]
            print(f"            Source {pos}: '{content}'")

        print(f"         🔍 DEBUG: Dest graph has {len(dest_graph)} cells")
        for pos, cell_data in list(dest_graph.items())[:2]:
            content = cell_data.get("content") or ""
            content = content[:20]
            print(f"            Dest {pos}: '{content}'")

        total_score = 0.0
        max_possible_score = len(source_graph)

        for cell_pos, source_cell in source_graph.items():
            cell_score = 0.0

            if cell_pos in dest_graph:
                dest_cell = dest_graph[cell_pos]

                content_match = self._fuzzy_match_text(
                    source_cell.get("content", ""), dest_cell.get("content", "")
                )
                if content_match > 0.85:
                    cell_score += 0.5

                neighbor_directions = ["up", "down", "left", "right"]
                neighbor_matches = 0
                neighbor_count = 0

                for direction in neighbor_directions:
                    source_neighbor = source_cell.get(direction)
                    dest_neighbor = dest_cell.get(direction)

                    if source_neighbor is not None and dest_neighbor is not None:
                        neighbor_count += 1
                        if (
                            self._fuzzy_match_text(source_neighbor, dest_neighbor)
                            > 0.85
                        ):
                            neighbor_matches += 1

                if neighbor_count > 0:
                    adjacency_score = neighbor_matches / neighbor_count
                    cell_score += 0.5 * adjacency_score

            if cell_score == 0.0:
                for dest_pos, dest_cell in dest_graph.items():
                    content_match = self._fuzzy_match_text(
                        source_cell.get("content", ""), dest_cell.get("content", "")
                    )
                    if content_match > 0.85:
                        neighbor_matches = 0
                        neighbor_total = 0

                        for direction in ["up", "down", "left", "right"]:
                            source_neighbor = source_cell.get(direction)
                            dest_neighbor = dest_cell.get(direction)

                            if (
                                source_neighbor is not None
                                and dest_neighbor is not None
                            ):
                                neighbor_total += 1
                                if (
                                    self._fuzzy_match_text(
                                        source_neighbor, dest_neighbor
                                    )
                                    > 0.85
                                ):
                                    neighbor_matches += 1

                        if neighbor_total > 0:
                            cell_score = 0.3 + (0.3 * neighbor_matches / neighbor_total)
                            break

            total_score += cell_score

        return total_score / max_possible_score if max_possible_score > 0 else 0.0

    def _build_dest_adjacency_graph(
        self, dest_table: TableStructure
    ) -> dict[tuple[int, int], dict[str, str | None]]:
        """Build adjacency graph sampling 5 key cells: corners and center."""
        if not dest_table.rows or not dest_table.rows[0]:
            return {}

        visible_rows = len(dest_table.rows)
        visible_cols = len(dest_table.rows[0])

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

            cell_content = dest_table.rows[row_idx][col_idx].strip()

            neighbors: dict[str, str | None] = {
                "content": cell_content,
                "up": (
                    dest_table.rows[row_idx - 1][col_idx].strip()
                    if row_idx > 0
                    else None
                ),
                "down": (
                    dest_table.rows[row_idx + 1][col_idx].strip()
                    if row_idx < visible_rows - 1
                    else None
                ),
                "left": (
                    dest_table.rows[row_idx][col_idx - 1].strip()
                    if col_idx > 0
                    else None
                ),
                "right": (
                    dest_table.rows[row_idx][col_idx + 1].strip()
                    if col_idx < visible_cols - 1
                    else None
                ),
            }

            graph[(row_idx, col_idx)] = neighbors

        return graph

    def _fuzzy_match_text(self, text1: str | None, text2: str | None) -> float:
        if not text1 or not text2:
            return 0.0

        t1 = text1.strip().lower()
        t2 = text2.strip().lower()

        if t1 == t2:
            return 1.0

        if HAS_RAPIDFUZZ and fuzz is not None:
            return float(fuzz.ratio(t1, t2) / 100.0)

        if t1 in t2 or t2 in t1:
            return 0.9

        return 0.0


class TableTransferer:
    """Transfers table redactions to destination PDF."""

    def transfer(
        self,
        source_redaction: TableRedaction,
        dest_page: fitz.Page,
        matched_table: fitz.table.Table,
        match_score: TableMatchScore | None = None,
    ) -> tuple[float, float, float, float] | None:
        """Calculate redaction position in destination table.

        Uses adjacency graph to find anchor cell, then applies relative offset.
        Falls back to normalized coordinates if no anchor found.
        """
        dest_table_bbox = matched_table.bbox
        if not dest_table_bbox:
            return None

        table_dict = matched_table.to_dict()
        dest_rows = table_dict.get("rows", [])
        if not dest_rows or not dest_rows[0]:
            return None

        anchor_cell_pos = self._find_best_anchor_cell(
            source_redaction.adjacency_graph, dest_rows
        )

        if anchor_cell_pos is None:
            print("         ⚠️  No anchor cell found, using normalized coordinates")
            return self._transfer_normalized(source_redaction, dest_table_bbox)

        cell_bboxes = matched_table.to_dict().get("cells", [])
        if not cell_bboxes:
            return self._transfer_normalized(source_redaction, dest_table_bbox)

        anchor_row, anchor_col = anchor_cell_pos
        anchor_bbox = self._get_cell_bbox(cell_bboxes, anchor_row, anchor_col)

        if not anchor_bbox:
            return self._transfer_normalized(source_redaction, dest_table_bbox)

        source_table_bbox = source_redaction.table_bbox
        source_cell_x0 = source_table_bbox[0] + source_redaction.relative_x0 * (
            source_table_bbox[2] - source_table_bbox[0]
        )
        source_cell_y0 = source_table_bbox[1] + source_redaction.relative_y0 * (
            source_table_bbox[3] - source_table_bbox[1]
        )

        offset_x = source_cell_x0 - source_table_bbox[0]
        offset_y = source_cell_y0 - source_table_bbox[1]

        dest_x0 = anchor_bbox[0] + offset_x
        dest_y0 = anchor_bbox[1] + offset_y

        original_width = (
            source_redaction.redaction_bbox[2] - source_redaction.redaction_bbox[0]
        )
        original_height = (
            source_redaction.redaction_bbox[3] - source_redaction.redaction_bbox[1]
        )

        dest_x1 = dest_x0 + original_width
        dest_y1 = dest_y0 + original_height

        print(
            f"         📍 Anchored to cell ({anchor_row},{anchor_col}) "
            f"at ({anchor_bbox[0]:.1f},{anchor_bbox[1]:.1f})"
        )

        return (dest_x0, dest_y0, dest_x1, dest_y1)

    def _transfer_normalized(
        self,
        source_redaction: TableRedaction,
        dest_table_bbox: tuple[float, float, float, float],
    ) -> tuple[float, float, float, float] | None:
        """Fallback transfer using normalized table-relative coordinates."""
        table_width = dest_table_bbox[2] - dest_table_bbox[0]
        table_height = dest_table_bbox[3] - dest_table_bbox[1]

        if table_width <= 0 or table_height <= 0:
            return None

        dest_x0 = dest_table_bbox[0] + source_redaction.relative_x0 * table_width
        dest_y0 = dest_table_bbox[1] + source_redaction.relative_y0 * table_height
        dest_x1 = dest_table_bbox[0] + source_redaction.relative_x1 * table_width
        dest_y1 = dest_table_bbox[1] + source_redaction.relative_y1 * table_height

        return (dest_x0, dest_y0, dest_x1, dest_y1)

    def _find_best_anchor_cell(
        self,
        adjacency_graph: dict[tuple[int, int], dict[str, str | None]],
        dest_rows: list[list[str]],
    ) -> tuple[int, int] | None:
        """Find best matching cell from adjacency graph to use as anchor.

        Requires minimum 2 matches (content + 1 neighbor, or 2 neighbors).
        """
        if not adjacency_graph:
            return None

        best_cell = None
        best_match_count = 0

        for cell_pos, cell_data in adjacency_graph.items():
            row_idx, col_idx = cell_pos

            if row_idx >= len(dest_rows) or col_idx >= len(dest_rows[0]):
                continue

            match_count = 0
            dest_cell_content = dest_rows[row_idx][col_idx].strip().lower()
            source_cell_content = (cell_data.get("content") or "").strip().lower()

            if source_cell_content == dest_cell_content:
                match_count += 2

            for direction in ["up", "down", "left", "right"]:
                source_neighbor = cell_data.get(direction)
                if source_neighbor is None:
                    continue

                dest_neighbor = self._get_neighbor_content(
                    dest_rows, row_idx, col_idx, direction
                )
                if (
                    dest_neighbor
                    and source_neighbor.strip().lower() == dest_neighbor.strip().lower()
                ):
                    match_count += 1

            if match_count > best_match_count:
                best_match_count = match_count
                best_cell = cell_pos

        if best_match_count >= 2:
            return best_cell

        return None

    def _get_neighbor_content(
        self, rows: list[list[str]], row: int, col: int, direction: str
    ) -> str | None:
        if direction == "up":
            if row > 0:
                return rows[row - 1][col]
        elif direction == "down":
            if row < len(rows) - 1:
                return rows[row + 1][col]
        elif direction == "left":
            if col > 0:
                return rows[row][col - 1]
        elif direction == "right":
            if col < len(rows[0]) - 1:
                return rows[row][col + 1]

        return None

    def _get_cell_bbox(
        self,
        cell_bboxes: list[list[tuple[float, float, float, float]]],
        row: int,
        col: int,
    ) -> tuple[float, float, float, float] | None:
        if row < len(cell_bboxes) and col < len(cell_bboxes[row]):
            return cell_bboxes[row][col]
        return None
