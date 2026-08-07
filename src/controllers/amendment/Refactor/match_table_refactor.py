from __future__ import annotations

import fitz

from src.core.state.app_state import RedactionBox, TableRedactionBox, TableMatchScore

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    fuzz = None  # type: ignore[assignment]


def match_table(
    table_box: TableRedactionBox,
    dest_doc: fitz.Document,
    source_page_idx: int,
    page_offset: int = 2,
) -> RedactionBox | None:
    print(f"[match_table] Matching table from page {source_page_idx + 1}")
    print(f"   Source table: {table_box.row_count}x{table_box.col_count}")
    print(
        f"   Headers: {table_box.headers[:3] if len(table_box.headers) > 3 else table_box.headers}"
    )
    print(f"   Title: {table_box.title}")
    print(f"   Search radius: ±{page_offset} pages")

    start_page = max(0, source_page_idx - page_offset)
    end_page = min(len(dest_doc) - 1, source_page_idx + page_offset)

    matcher = TableMatcher()
    best_match = None
    best_match_page_idx = None
    best_score = 0.0

    for page_idx in range(start_page, end_page + 1):
        dest_page = dest_doc[page_idx]
        print(f"   Checking destination page {page_idx + 1}...")
        match_score = matcher.find_best_match(dest_page, table_box)

        if match_score:
            print(f"      Match found! Score: {match_score.total_score:.2f}")

        if match_score and match_score.total_score > best_score:
            best_match = match_score
            best_match_page_idx = page_idx
            best_score = match_score.total_score

    if not best_match or best_match_page_idx is None:
        print(f"   ❌ No match found (threshold: {matcher.MATCH_THRESHOLD})")
        return None

    print(
        f"   ✓ Best match: score={best_match.total_score:.2f} on page {best_match_page_idx + 1}"
    )

    transferer = TableTransferer()
    transferred_bbox = transferer.transfer(table_box, best_match)

    if not transferred_bbox:
        return None

    return RedactionBox(
        id=table_box.id,
        x=float(transferred_bbox[0]),
        y=float(transferred_bbox[1]),
        w=float(transferred_bbox[2] - transferred_bbox[0]),
        h=float(transferred_bbox[3] - transferred_bbox[1]),
        page=best_match_page_idx + 1,
        selection_mode=table_box.selection_mode,
        term=table_box.term,
        match=table_box.match,
        batch_id=table_box.batch_id,
    )


class TableMatcher:
    ADJACENCY_WEIGHT = 0.30
    STRUCTURE_WEIGHT = 0.30
    HEADER_WEIGHT = 0.25
    TITLE_WEIGHT = 0.15
    POSITION_WEIGHT = 0.0

    MATCH_THRESHOLD = 0.40

    def find_best_match(
        self, dest_page: fitz.Page, source_table: TableRedactionBox
    ) -> TableMatchScore | None:
        tables = dest_page.find_tables()
        if not tables or not tables.tables:
            print("         No tables found on destination page")
            return None

        print(f"         Found {len(tables.tables)} table(s) on destination page")
        best_score: TableMatchScore | None = None

        for idx, table_obj in enumerate(tables.tables):
            rows = table_obj.extract()

            if not rows or not rows[0]:
                continue

            row_count = len(rows)
            col_count = len(rows[0])

            structure_score = self._score_structure(
                source_table.row_count, source_table.col_count, row_count, col_count
            )
            header_score = self._score_headers(
                source_table.headers, rows[0] if rows else []
            )
            title_score = self._score_title(
                source_table.title, dest_page, table_obj.bbox
            )
            position_score = 0.0

            adjacency_score = self._score_adjacency_graph(
                source_table.adjacency_graph, rows
            )

            total_score = (
                adjacency_score * self.ADJACENCY_WEIGHT
                + structure_score * self.STRUCTURE_WEIGHT
                + header_score * self.HEADER_WEIGHT
                + title_score * self.TITLE_WEIGHT
                + position_score * self.POSITION_WEIGHT
            )

            table_bbox = table_obj.bbox
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

            match_score = TableMatchScore(
                table_idx=idx,
                adjacency_score=adjacency_score,
                structure_score=structure_score,
                header_score=header_score,
                title_score=title_score,
                position_score=position_score,
                total_score=total_score,
                table_bbox=bbox_tuple,
            )

            print(
                f"         Table {idx}: {row_count}x{col_count} → "
                f"score={total_score:.2f} (adj={adjacency_score:.2f}, "
                f"struct={structure_score:.2f}, hdr={header_score:.2f}, "
                f"title={title_score:.2f})"
            )

            if best_score is None or total_score > best_score.total_score:
                best_score = match_score

        if best_score and best_score.total_score >= self.MATCH_THRESHOLD:
            return best_score

        if best_score:
            print(
                f"         Best score {best_score.total_score:.2f} below threshold {self.MATCH_THRESHOLD}"
            )

        return None

    def _score_structure(
        self, source_row: int, source_col: int, dest_row: int, dest_col: int
    ) -> float:
        if source_col == dest_col and source_row == dest_row:
            return 1.0

        col_diff = abs(source_col - dest_col)
        row_diff = abs(source_row - dest_row)

        max_diff = 5

        col_score = max(0.0, 1.0 - (col_diff / max_diff))
        row_score = max(0.0, 1.0 - (row_diff / max_diff))

        return (col_score + row_score) / 2.0

    def _score_headers(
        self, source_headers: list[str], dest_headers: list[str]
    ) -> float:
        if not source_headers or not dest_headers:
            return 1.0

        comparisons = min(len(source_headers), len(dest_headers))

        if not HAS_RAPIDFUZZ or fuzz is None:
            matches = sum(
                1
                for i in range(comparisons)
                if str(source_headers[i] or "").strip()
                == str(dest_headers[i] or "").strip()
            )
            return matches / comparisons if comparisons > 0 else 0.0

        total_similarity = 0.0

        for i in range(comparisons):
            source_header = str(source_headers[i] or "").strip()
            dest_header = str(dest_headers[i] or "").strip()

            if not source_header and not dest_header:
                total_similarity += 1.0
            elif not source_header or not dest_header:
                total_similarity += 0.0
            else:
                similarity_score = float(fuzz.ratio(source_header, dest_header)) / 100.0
                total_similarity += similarity_score

        return total_similarity / comparisons if comparisons > 0 else 0.0

    def _score_title(
        self,
        source_title: str | None,
        dest_page: fitz.Page,
        dest_table_bbox: tuple[float, float, float, float],
    ) -> float:
        # Search 50px above table for title text
        search_rect = fitz.Rect(
            dest_table_bbox[0],
            max(0, dest_table_bbox[1] - 50),
            dest_table_bbox[2],
            dest_table_bbox[1],
        )
        text = dest_page.get_text("text", clip=search_rect).strip()
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        dest_title = lines[-1] if lines else None

        if not source_title and not dest_title:
            return 1.0

        if not source_title or not dest_title:
            return 0.5

        if not HAS_RAPIDFUZZ or fuzz is None:
            return 1.0 if source_title == dest_title else 0.0

        return float(fuzz.ratio(source_title, dest_title)) / 100.0

    def _score_adjacency_graph(
        self,
        source_graph: dict[tuple[int, int], dict[str, str | None]],
        dest_rows: list[list[str]],
    ) -> float:
        # Adjacency graph: verify key cells and their neighbors match between source/dest tables
        if not source_graph:
            return 0.0

        dest_graph = self._build_dest_adjacency_graph(dest_rows)
        if not dest_graph:
            return 0.0

        total_score = 0.0
        max_possible_score = len(source_graph)

        for cell_pos, source_cell in source_graph.items():
            cell_score = 0.0

            # First try: match at same position
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

            # Fallback: search any position for content + neighbor match
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

        return total_score / max_possible_score

    def _build_dest_adjacency_graph(
        self, dest_rows: list[list[str]]
    ) -> dict[tuple[int, int], dict[str, str | None]]:
        # Sample key corner/center positions to build lightweight adjacency graph
        if not dest_rows or not dest_rows[0]:
            return {}

        visible_rows = len(dest_rows)
        visible_cols = len(dest_rows[0])

        key_positions = [
            (0, 0),
            (0, visible_cols - 1),
            (visible_rows - 1, 0),
            (visible_rows - 1, visible_cols - 1),
            (visible_rows // 2, visible_cols // 2),
        ]

        graph: dict[tuple[int, int], dict[str, str | None]] = {}

        def safe_cell(r: int, c: int) -> str | None:
            if r < 0 or r >= visible_rows or c < 0 or c >= visible_cols:
                return None
            val = dest_rows[r][c]
            return str(val).strip() if val is not None else ""

        for row_idx, col_idx in key_positions:
            if row_idx >= visible_rows or col_idx >= visible_cols:
                continue

            cell = dest_rows[row_idx][col_idx]
            cell_content = str(cell).strip() if cell is not None else ""

            neighbors: dict[str, str | None] = {
                "content": cell_content,
                "up": safe_cell(row_idx - 1, col_idx),
                "down": safe_cell(row_idx + 1, col_idx),
                "left": safe_cell(row_idx, col_idx - 1),
                "right": safe_cell(row_idx, col_idx + 1),
            }

            graph[(row_idx, col_idx)] = neighbors

        return graph

    def _fuzzy_match_text(self, text1: str | None, text2: str | None) -> float:
        if text1 is None or text2 is None:
            return 0.0

        t1 = str(text1).strip().lower()
        t2 = str(text2).strip().lower()

        if not t1 and not t2:
            return 1.0

        if not t1 or not t2:
            return 0.0

        if t1 == t2:
            return 1.0

        if HAS_RAPIDFUZZ and fuzz is not None:
            return float(fuzz.ratio(t1, t2) / 100.0)

        return 0.9 if t1 in t2 or t2 in t1 else 0.0


class TableTransferer:
    def transfer(
        self, source_table: TableRedactionBox, match_score: TableMatchScore
    ) -> tuple[float, float, float, float] | None:
        # Calculate relative position of redaction box within source table,
        # then apply same relative position to destination table
        source_bbox = (
            source_table.x,
            source_table.y,
            source_table.x + source_table.w,
            source_table.y + source_table.h,
        )
        source_table_bbox = source_table.table_bbox

        source_width = source_table_bbox[2] - source_table_bbox[0]
        source_height = source_table_bbox[3] - source_table_bbox[1]

        if source_width <= 0 or source_height <= 0:
            return None

        relative_x0 = (source_bbox[0] - source_table_bbox[0]) / source_width
        relative_y0 = (source_bbox[1] - source_table_bbox[1]) / source_height
        relative_x1 = (source_bbox[2] - source_table_bbox[0]) / source_width
        relative_y1 = (source_bbox[3] - source_table_bbox[1]) / source_height

        dest_table_bbox = match_score.table_bbox
        dest_width = dest_table_bbox[2] - dest_table_bbox[0]
        dest_height = dest_table_bbox[3] - dest_table_bbox[1]

        if dest_width <= 0 or dest_height <= 0:
            return None

        dest_x0 = dest_table_bbox[0] + relative_x0 * dest_width
        dest_y0 = dest_table_bbox[1] + relative_y0 * dest_height
        dest_x1 = dest_table_bbox[0] + relative_x1 * dest_width
        dest_y1 = dest_table_bbox[1] + relative_y1 * dest_height

        return (dest_x0, dest_y0, dest_x1, dest_y1)
