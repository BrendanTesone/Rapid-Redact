# no comments below this point

from __future__ import annotations

import uuid

import fitz

from src.core.state.app_state import RedactionBox, SelectionMode


def print_redline_coords(pdf_path: str, page_num: int) -> None:
    doc = fitz.open(pdf_path)
    page_index = page_num - 1

    if page_index < 0 or page_index >= len(doc):
        doc.close()
        raise ValueError(f"Page {page_num} out of range (1-{len(doc)} available)")

    page = doc[page_index]
    raw_boxes = _extract_page_redactions(page, page_index)
    doc.close()

    print("\n" + "=" * 60)
    print(f"RAW REDLINE COORDINATES: Page {page_num}")
    print("=" * 60)
    print(f"Total raw redactions: {len(raw_boxes)}\n")

    for i, redaction in enumerate(raw_boxes, 1):
        detection_method = redaction.match or "unknown"
        print(f"[{i}] RAW (found by: {detection_method})")
        print(
            f"    x={redaction.x:.2f}, y={redaction.y:.2f}, w={redaction.w:.2f}, h={redaction.h:.2f}"
        )
        print()

    print("=" * 60 + "\n")


def _extract_page_redactions(page: fitz.Page, page_idx: int) -> list[RedactionBox]:
    redactions = []

    def should_extract_pass1(annot_type: int, subject: str) -> bool:
        return annot_type == 25

    def should_extract_pass2(annot_type: int, subject: str) -> bool:
        return subject == "Redact"

    def should_extract_pass3(annot_type: int, subject: str) -> bool:
        return "redact" in subject.lower()

    def should_extract_pass4(annot_type: int, subject: str) -> bool:
        return annot_type == 13

    detection_methods = [
        (should_extract_pass1, "Type 25 (Official Redact)"),
        (should_extract_pass2, "Subject='Redact' (Exact)"),
        (should_extract_pass3, "Subject contains 'redact'"),
        (should_extract_pass4, "Type 13 (Stamp)"),
    ]

    annot = page.first_annot
    while annot:
        annot_type = annot.type[0]
        subject = annot.info.get("subject", "").strip()

        for detection_func, method_name in detection_methods:
            if detection_func(annot_type, subject):
                rect = annot.rect
                vertices = annot.vertices if hasattr(annot, "vertices") else None

                if vertices:
                    extracted_boxes = _extract_from_vertices(
                        vertices, page, page_idx, method_name
                    )
                else:
                    extracted_boxes = [
                        _extract_from_rectangle(rect, page, page_idx, method_name)
                    ]

                redactions.extend(extracted_boxes)
                break

        annot = annot.next

    return redactions


def _extract_from_vertices(
    vertices: list[tuple[float, float]],
    page: fitz.Page,
    page_idx: int,
    method_name: str,
) -> list[RedactionBox]:
    num_lines = len(vertices) // 4
    line_boxes = []

    for line_idx in range(num_lines):
        line_vertices = vertices[line_idx * 4 : (line_idx + 1) * 4]

        x_coords = [v[0] for v in line_vertices]
        y_coords = [v[1] for v in line_vertices]
        min_x, max_x = min(x_coords), max(x_coords)
        min_y, max_y = min(y_coords), max(y_coords)

        line_box = RedactionBox(
            id=str(uuid.uuid4()),
            x=float(min_x),
            y=float(min_y),
            w=float(max_x - min_x),
            h=float(max_y - min_y),
            page=page_idx + 1,
            selection_mode=SelectionMode.HIGHLIGHT,
            term="raw",
            match=method_name,
            batch_id=None,
        )
        line_boxes.append(line_box)

    return line_boxes


def _extract_from_rectangle(
    rect: fitz.Rect, page: fitz.Page, page_idx: int, method_name: str
) -> RedactionBox:
    rect_box = RedactionBox(
        id=str(uuid.uuid4()),
        x=float(rect.x0),
        y=float(rect.y0),
        w=float(rect.x1 - rect.x0),
        h=float(rect.y1 - rect.y0),
        page=page_idx + 1,
        selection_mode=SelectionMode.RECTANGLE,
        term="raw",
        match=method_name,
        batch_id=None,
    )

    return rect_box
