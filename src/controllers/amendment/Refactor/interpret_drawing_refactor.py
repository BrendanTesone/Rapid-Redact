from __future__ import annotations

import uuid

import fitz

from src.core.state.app_state import RedactionBox, SelectionMode
from src.controllers.amendment.Refactor.drawing_cluster_utils import (
    extract_drawing_clusters,
)
from src.controllers.amendment.Refactor.interpret_text_refactor import interpret_text


def interpret_drawing(
    raw_box: RedactionBox, page: fitz.Page, page_idx: int
) -> list[RedactionBox]:
    interpreted_boxes = []

    raw_rect = fitz.Rect(
        raw_box.x, raw_box.y, raw_box.x + raw_box.w, raw_box.y + raw_box.h
    )

    page_drawings = page.get_drawings()
    all_clusters = extract_drawing_clusters(page_drawings, expansion_radius=100)

    overlapping_clusters = []
    for cluster in all_clusters:
        cluster_rect = cluster["rect"]
        _ = raw_rect & cluster_rect
        overlapping_clusters.append(cluster)

    best_cluster = max(overlapping_clusters, key=lambda c: c["count"])

    drawing_box = _create_drawing_cluster_box(best_cluster, page_idx)
    interpreted_boxes.append(drawing_box)

    text_boxes = interpret_text(raw_box, page, page_idx)
    interpreted_boxes.extend(text_boxes)

    return interpreted_boxes


def _create_drawing_cluster_box(
    cluster: dict[str, fitz.Rect | int], page_idx: int
) -> RedactionBox:
    cluster_rect = cluster["rect"]
    cluster_count = cluster["count"]

    metrics = _create_metrics_signature(cluster_rect, cluster_count)

    return RedactionBox(
        id=str(uuid.uuid4()),
        x=float(cluster_rect.x0),
        y=float(cluster_rect.y0),
        w=float(cluster_rect.width),
        h=float(cluster_rect.height),
        page=page_idx + 1,
        selection_mode=SelectionMode.RECTANGLE,
        term="DRAWING_CLUSTER",
        match=metrics,
        batch_id=None,
    )


def parse_metrics(metrics_str: str | None) -> dict[str, float]:
    result = {
        key: float(value)
        for part in metrics_str.split("|")  # type: ignore[union-attr]
        for key, value in [part.split(":", 1)]
    }
    result["width"] = result.pop("w")
    result["height"] = result.pop("h")
    return result


def _create_metrics_signature(cluster_rect: fitz.Rect, drawing_count: int) -> str:
    w, h = cluster_rect.width, cluster_rect.height
    area = w * h
    return f"count:{drawing_count}|w:{w:.1f}|h:{h:.1f}|aspect:{w/h:.3f}|density:{drawing_count/area:.6f}"
