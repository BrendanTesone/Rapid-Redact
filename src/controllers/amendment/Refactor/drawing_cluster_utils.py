from __future__ import annotations

import fitz


def extract_drawing_clusters(
    drawings: list[dict[str, tuple[float, float, float, float]]],
    expansion_radius: int = 100,
    min_cluster_size: int = 1,
) -> list[dict[str, fitz.Rect | int]]:
    parent: dict[int, int] = {}
    for i in range(len(drawings)):
        parent[i] = i

    def find(x: int) -> int:
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x: int, y: int) -> None:
        root_x = find(x)
        root_y = find(y)
        if root_x != root_y:
            parent[root_x] = root_y

    for i, d1 in enumerate(drawings):
        rect1 = fitz.Rect(d1["rect"])
        expanded1 = fitz.Rect(
            rect1.x0 - expansion_radius,
            rect1.y0 - expansion_radius,
            rect1.x1 + expansion_radius,
            rect1.y1 + expansion_radius,
        )

        for j, d2 in enumerate(drawings):
            if i >= j:
                continue

            rect2 = fitz.Rect(d2["rect"])
            if expanded1.intersects(rect2):
                union(i, j)

    clusters_dict: dict[int, list[dict[str, tuple[float, float, float, float]]]] = {}
    for i in range(len(drawings)):
        root = find(i)
        if root not in clusters_dict:
            clusters_dict[root] = []
        clusters_dict[root].append(drawings[i])

    clusters: list[dict[str, fitz.Rect | int]] = []
    for cluster_drawings in clusters_dict.values():
        rects = [fitz.Rect(d["rect"]) for d in cluster_drawings]
        union_rect = rects[0]
        for rect in rects[1:]:
            union_rect |= rect

        clusters.append({"rect": union_rect, "count": len(cluster_drawings)})

    return clusters


def calculate_raw_box_cluster_overlap(
    raw_box_rect: fitz.Rect, cluster_rect: fitz.Rect
) -> float:
    intersection = raw_box_rect & cluster_rect
    raw_box_area = raw_box_rect.get_area()

    return float(intersection.get_area() / raw_box_area)
