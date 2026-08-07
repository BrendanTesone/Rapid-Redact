from __future__ import annotations

import fitz

from src.core.state.app_state import RedactionBox
from src.controllers.amendment.Refactor.drawing_cluster_utils import (
    extract_drawing_clusters,
)
from src.controllers.amendment.Refactor.interpret_drawing_refactor import parse_metrics


def match_drawing(
    drawing_box: RedactionBox,
    dest_doc: fitz.Document,
    source_page_idx: int,
    page_offset: int = 2,
) -> RedactionBox | None:
    source_metrics = parse_metrics(drawing_box.match)

    start_page = max(0, source_page_idx - page_offset)
    end_page = min(len(dest_doc) - 1, source_page_idx + page_offset)

    best_score = 0.0
    best_cluster = {}
    best_match_page = source_page_idx

    for page_idx in range(start_page, end_page + 1):
        dest_page = dest_doc[page_idx]
        drawings = dest_page.get_drawings()

        clusters = extract_drawing_clusters(drawings, expansion_radius=100)

        for cluster in clusters:
            cluster_rect = cluster["rect"]
            cluster_count = cluster["count"]

            score = _score_cluster_similarity(
                source_metrics, cluster_rect, cluster_count
            )

            if score > best_score:
                best_score = score
                best_cluster = cluster
                best_match_page = page_idx

    cluster_rect_val = best_cluster["rect"]
    matched_box = RedactionBox(
        id=drawing_box.id,
        x=float(cluster_rect_val.x0),
        y=float(cluster_rect_val.y0),
        w=float(cluster_rect_val.x1 - cluster_rect_val.x0),
        h=float(cluster_rect_val.y1 - cluster_rect_val.y0),
        page=best_match_page + 1,
        selection_mode=drawing_box.selection_mode,
        term=drawing_box.term,
        match=drawing_box.match,
        batch_id=drawing_box.batch_id,
    )
    return matched_box


def _score_cluster_similarity(
    source_metrics: dict[str, float], dest_rect: fitz.Rect, dest_count: int
) -> float:
    source_count = source_metrics["count"]
    source_width = source_metrics["width"]
    source_height = source_metrics["height"]
    source_aspect = source_metrics["aspect"]
    source_density = source_metrics["density"]

    dest_width = dest_rect.width
    dest_height = dest_rect.height
    dest_aspect = dest_width / dest_height
    dest_area = dest_width * dest_height
    dest_density = dest_count / dest_area

    count_score = 1.0 - abs(source_count - dest_count) / max(source_count, dest_count)

    width_score = 1.0 - abs(source_width - dest_width) / max(source_width, dest_width)
    height_score = 1.0 - abs(source_height - dest_height) / max(
        source_height, dest_height
    )
    dim_score = (width_score + height_score) / 2.0

    aspect_score = 1.0 - abs(source_aspect - dest_aspect) / max(
        source_aspect, dest_aspect
    )

    density_score = 1.0 - abs(source_density - dest_density) / max(
        source_density, dest_density
    )

    return (
        (count_score * 0.2)
        + (dim_score * 0.3)
        + (aspect_score * 0.2)
        + (density_score * 0.3)
    )
