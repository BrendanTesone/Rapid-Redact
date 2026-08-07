from __future__ import annotations


import fitz

from src.core.state.app_state import RedactionBox, SelectionMode


def interpret_text(
    raw_box: RedactionBox, page: fitz.Page, page_idx: int
) -> list[RedactionBox]:
    print(
        f"[interpret_text] Called for raw_box on page {page_idx + 1}: x={raw_box.x:.2f}, y={raw_box.y:.2f}, w={raw_box.w:.2f}, h={raw_box.h:.2f}"
    )
    rect = fitz.Rect(raw_box.x, raw_box.y, raw_box.x + raw_box.w, raw_box.y + raw_box.h)

    if raw_box.selection_mode == SelectionMode.HIGHLIGHT:
        text_content, context = _extract_text_with_context(
            page, rect, context_radius=50
        )

        text_box = RedactionBox(
            id=raw_box.id,
            x=raw_box.x,
            y=raw_box.y,
            w=raw_box.w,
            h=raw_box.h,
            page=raw_box.page,
            selection_mode=raw_box.selection_mode,
            term="TEXT",
            match=text_content,
            context=context,
            batch_id=raw_box.batch_id,
        )
        return [text_box]
    else:
        return _split_rectangle_into_lines(rect, page, page_idx, raw_box)


def _split_rectangle_into_lines(
    rect: fitz.Rect, page: fitz.Page, page_idx: int, raw_box: RedactionBox
) -> list[RedactionBox]:
    text_content, context = _extract_text_with_context(page, rect, context_radius=50)

    if not text_content:
        return []

    return [
        RedactionBox(
            id=raw_box.id,
            x=raw_box.x,
            y=raw_box.y,
            w=raw_box.w,
            h=raw_box.h,
            page=raw_box.page,
            selection_mode=SelectionMode.HIGHLIGHT,
            term="TEXT",
            match=text_content,
            context=context,
            batch_id=raw_box.batch_id,
        )
    ]


def _extract_text_from_rect(page: fitz.Page, rect: fitz.Rect) -> str:
    text = page.get_text("text", clip=rect).strip()
    return " ".join(text.split())


def _extract_text_with_context(
    page: fitz.Page,
    rect: fitz.Rect,
    context_radius: int = 50,
) -> tuple[str, str]:
    redacted_text = page.get_text("text", clip=rect).strip()
    redacted_text = " ".join(redacted_text.split())

    if not redacted_text:
        return "", ""

    page_text = page.get_text("text")
    normalized_page = " ".join(page_text.split())
    match_start = normalized_page.find(redacted_text)

    if match_start == -1:
        first_words = " ".join(redacted_text.split()[:3])
        match_start = normalized_page.find(first_words)

    if match_start == -1:
        return redacted_text, ""

    match_end = match_start + len(redacted_text)
    context_start = max(0, match_start - context_radius)
    context_end = min(len(normalized_page), match_end + context_radius)

    context_before = normalized_page[context_start:match_start].lstrip()

    # Avoid cutting words in half at context boundaries
    if context_start > 0 and not normalized_page[context_start - 1].isspace():
        space_idx = context_before.find(" ")
        if space_idx != -1:
            context_before = context_before[space_idx + 1 :]

    context_after = normalized_page[match_end:context_end].rstrip()
    if (
        context_end < len(normalized_page)
        and not normalized_page[context_end].isspace()
    ):
        space_idx = context_after.rfind(" ")
        if space_idx != -1:
            context_after = context_after[:space_idx]

    context = f"{context_before} {redacted_text} {context_after}".strip()

    return redacted_text, context
