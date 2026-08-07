from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import flet as ft

from src.core.state.app_state import AppState

if TYPE_CHECKING:
    pass


def build_page_strip_item(
    page_idx: int,
    is_current: bool,
    has_gap: bool,
    has_match: bool,
    has_redactions: bool,
    redaction_count: int,
    on_click_handler: Callable[[ft.ControlEvent], None],
) -> ft.Container:
    tooltip_parts: list[str] = [f"Page {page_idx + 1}"]

    # Styling priority: current > gap/match > redactions > default
    if is_current:
        bg = "#2196F3"
        fg = "white"
        border = None
    elif has_gap or has_match:
        bg = "#FF9800"
        fg = "white"
        border = None
        if has_gap:
            tooltip_parts.append("Consistency gap")
        if has_match:
            tooltip_parts.append("Search match")
    elif has_redactions:
        bg = "#F44336"
        fg = "white"
        border = None
        tooltip_parts.append(f"{redaction_count} redaction(s)")
    else:
        bg = "grey200"
        fg = "grey600"
        border = None

    tooltip = " - ".join(tooltip_parts)

    return ft.Container(
        content=ft.Text(
            str(page_idx + 1), size=7, color=fg, text_align="center", weight="bold"
        ),
        width=28,
        height=20,
        bgcolor=bg,
        border=border,
        border_radius=3,
        alignment=ft.alignment.center,
        tooltip=tooltip,
        on_click=on_click_handler,
    )


def build_page_placeholder(
    page_idx: int,
    base_width: int,
    zoom: float,
    page_height: float | None = None,
    fallback_page_height: float = 1035.5,
) -> ft.Container:
    placeholder_height = page_height if page_height else fallback_page_height * zoom

    return ft.Container(
        width=base_width * zoom,
        height=placeholder_height,
        bgcolor="#F0F0F0",
        alignment=ft.alignment.center,
        content=ft.Text(f"Page {page_idx + 1}", size=20, color="grey"),
    )


def build_pdf_page_image(
    img_data: str, width: float, height: float, scale: float
) -> ft.Image:
    return ft.Image(
        src_base64=img_data,
        fit=ft.ImageFit.NONE,
        width=width * scale,
        height=height * scale,
    )


def build_pdf_page_gesture_detector(
    pdf_image: ft.Image,
    page_index: int,
    on_pan_start: Callable[[ft.DragStartEvent, int], None],
    on_pan_update: Callable[[ft.DragUpdateEvent, int], None],
    on_pan_end: Callable[[ft.DragEndEvent, int], None],
    on_tap: Callable[[ft.ControlEvent], None],
    on_hover: Callable[[ft.HoverEvent, int], None] | None = None,
) -> ft.GestureDetector:
    gesture_detector = ft.GestureDetector(
        content=pdf_image,
        on_pan_start=lambda e, p=page_index: on_pan_start(e, p),
        on_pan_update=lambda e, p=page_index: on_pan_update(e, p),
        on_pan_end=lambda e, p=page_index: on_pan_end(e, p),
        on_tap=lambda e: on_tap(e),
        drag_interval=50,  # Throttle to 50ms (~20 updates/sec) for smooth highlighting
    )

    if on_hover:
        from src.core.state.ui_state import refs

        ref_key = f"page_{page_index}_gesture"
        if ref_key not in refs:
            refs[ref_key] = ft.Ref[ft.MouseRegion]()

        mouse_region = ft.MouseRegion(
            ref=refs[ref_key],
            content=gesture_detector,
            on_hover=lambda e, p=page_index: on_hover(e, p),
            mouse_cursor=ft.MouseCursor.BASIC,
        )
        return mouse_region

    return gesture_detector


def build_page_stack_container(
    controls: list[ft.Control], width: float, height: float, scale: float
) -> ft.Container:
    stack = ft.Stack(controls=controls, width=width * scale, height=height * scale)
    return ft.Container(content=stack, alignment=ft.alignment.top_center)


def get_pages_with_matches(state: AppState, file_name: str | None) -> set[int]:
    """
    Returns 0-based page indices with search matches, filtered by current tab:
    - matches tab: non-dose, non-consistency results only
    - dose tab: dose results (CCI:dosing) only
    - consistency tab: consistency gaps only
    - ai_detect tab: AI-detected results only
    - viewer/other tabs: no indicators (empty set)
    """
    if not file_name:
        return set()

    current_tab = state.ui.current_tab

    if current_tab not in ("matches", "dose", "consistency", "ai_detect"):
        return set()

    pages_with_matches: set[int] = set()

    if current_tab == "consistency":
        from src.core.state.app_state import ResultCategory

        for result in state.search.all_search_results:
            if (
                result.category == ResultCategory.GAP
                and result.file_name == file_name
                and result.page >= 1
            ):
                pages_with_matches.add(result.page - 1)
        return pages_with_matches

    if current_tab == "ai_detect":
        for result in state.search.all_search_results:
            if (
                result.file_name == file_name
                and result.term.startswith("AI:")
                and result.page >= 1
            ):
                pages_with_matches.add(result.page - 1)
        return pages_with_matches

    term_filter = state.search.results_term_filter or ""

    for result in state.search.all_search_results:
        if result.file_name == file_name:
            if current_tab == "matches" and result.term in (
                "CCI:dosing",
                "CCI:consistency",
            ):
                continue
            elif current_tab == "dose" and result.term != "CCI:dosing":
                continue

            if term_filter and result.term != term_filter:
                continue

            page_num: int = result.page
            if isinstance(page_num, int) and page_num >= 1:
                pages_with_matches.add(page_num - 1)

    return pages_with_matches
