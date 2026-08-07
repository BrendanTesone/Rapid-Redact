"""
redaction_rendering_controller.py - Visual rendering of redaction overlays
"""

from __future__ import annotations

import logging
from typing import Protocol, Callable

import flet as ft

from src.core.domain.pdf_coordinates import ScreenBox, to_screen_rect
from src.controllers.redaction.data_controller import RedactionDataController
from src.core.state.app_state import (
    AppState,
    RedactionBox,
    PdfBox,
    SearchResult,
    HighlightMode,
    HighlightFilter,
)

logger = logging.getLogger(__name__)


class SearchResultsControllerProtocol(Protocol):
    def dismiss_match(self, item: SearchResult) -> None: ...


class MainControllerProtocol(Protocol):
    state: AppState
    search: object
    viewer: object
    redaction_interaction: object
    consistency: object

    @property
    def search_results(self) -> SearchResultsControllerProtocol: ...


def _safe_update(control: object) -> bool:
    """Safely call update() on a control if it's attached to a page."""
    if control is None:
        return False
    if getattr(control, "page", None) is not None:
        control.update()  # type: ignore[attr-defined]
        return True
    return False


def get_highlight_mode(current_term: str) -> HighlightMode:
    normalized = current_term.strip().lower()
    if not normalized or normalized == "all":
        return HighlightMode.ALL_TERMS
    return HighlightMode.SINGLE_TERM


def should_highlight_result(
    result: SearchResult, filter_config: HighlightFilter
) -> bool:
    """Determine if a search result should be highlighted.

    Filtering stages:
    1. File/page matching
    2. Redaction status (skip if redacted/dismissed)
    3. Category filter
    4. Term matching (mode-dependent)
    """
    if result.file_name != filter_config.current_file:
        return False
    if result.page != filter_config.current_page:
        return False

    if result.redacted or result.dismissed:
        return False

    if filter_config.category_filter is not None:
        if result.category != filter_config.category_filter:
            return False

    if filter_config.mode == HighlightMode.NONE:
        return False
    elif filter_config.mode == HighlightMode.ALL_TERMS:
        return True
    else:
        term_lower = filter_config.term.lower()
        result_term_lower = result.term.lower()
        result_match_lower = (result.match or "").lower()
        return result_term_lower == term_lower or result_match_lower == term_lower


def filter_results_for_page(
    all_results: list[SearchResult], filter_config: HighlightFilter
) -> list[SearchResult]:
    return [
        result
        for result in all_results
        if should_highlight_result(result, filter_config)
    ]


class RedactionRenderingController:
    """Handles visual rendering of redaction overlays on PDF pages."""

    def __init__(
        self,
        main_controller: MainControllerProtocol,
        page: ft.Page,
        data_controller: RedactionDataController,
    ) -> None:
        self.main_controller = main_controller
        self.page = page
        self.data = data_controller
        self._handle_controls: dict[str, list[ft.Container]] = {}

    @property
    def state(self) -> AppState:
        return self.main_controller.state

    def build_page_overlays(self, page_index: int, scale: float) -> list[ft.Control]:
        """Build overlay controls for current page (search highlights + gaps + redactions)."""
        overlays: list[ft.Control] = []

        current_file = self.state.viewer.file_name or ""
        if current_file:
            current_term = self.main_controller.state.search.current_term or ""
            mode = get_highlight_mode(current_term)

            from src.core.state.app_state import ResultCategory

            current_tab = self.state.ui.current_tab
            if current_tab in ("matches", "dose", "consistency", "ai_detect"):
                filter_tab = current_tab
            else:
                filter_tab = None

            if filter_tab is not None:
                category_filter: ResultCategory | None = None
                if filter_tab == "matches":
                    category_filter = ResultCategory.MATCHES
                elif filter_tab == "dose":
                    category_filter = ResultCategory.DOSAGE
                elif filter_tab == "consistency":
                    category_filter = ResultCategory.GAP
                elif filter_tab == "ai_detect":
                    category_filter = ResultCategory.AI

                filter_config = HighlightFilter(
                    current_file=current_file,
                    current_page=page_index + 1,
                    mode=mode,
                    term=current_term if mode == HighlightMode.SINGLE_TERM else "",
                    category_filter=category_filter,
                )

                results_to_highlight = filter_results_for_page(
                    self.state.search.all_search_results, filter_config
                )

                for result in results_to_highlight:
                    overlays.extend(self._create_search_result_overlays(result, scale))

        current_tab = self.state.ui.current_tab
        filter_tab_consistency = current_tab if current_tab == "consistency" else None

        if filter_tab_consistency is not None:
            from src.core.state.app_state import ResultCategory

            current_file = self.main_controller.state.viewer.file_name or ""
            page_1b = page_index + 1

            for result in self.main_controller.state.search.all_search_results:
                if result.category != ResultCategory.GAP:
                    continue

                if result.redacted or result.dismissed:
                    continue

                if result.file_name != current_file or result.page != page_1b:
                    continue

                if not result.rects:
                    continue
                rect = result.rects[0]

                s = to_screen_rect(rect, scale)

                gap_text = (
                    result.match[:30] + "..."
                    if len(result.match) > 30
                    else result.match
                )

                def make_gap_click_handler(
                    result: SearchResult,
                ) -> Callable[[ft.ControlEvent], None]:
                    def handler(e: ft.ControlEvent) -> None:
                        from src.ui.views import base_results_view

                        base_results_view.add_result_redaction(result)

                    return handler

                overlays.append(
                    ft.Container(
                        left=s.x,
                        top=s.y,
                        width=s.w,
                        height=s.h,
                        bgcolor="#80FFFF00",
                        border=ft.border.all(2, "#FF9800"),
                        border_radius=2,
                        tooltip=f"Consistency gap: '{gap_text}' (click to redact)",
                        on_click=make_gap_click_handler(result),
                    )
                )
        selected_ids = self.main_controller.state.redaction.selected_annotation_ids

        fname = self.main_controller.state.viewer.file_name or ""
        page_reds = self.state.project.redactions.get(fname, {}).get(page_index, [])

        for redaction_box in page_reds:
            pdf_box = PdfBox(
                x=redaction_box.x,
                y=redaction_box.y,
                w=redaction_box.w,
                h=redaction_box.h,
            )
            s = to_screen_rect(pdf_box, scale)
            is_selected = redaction_box.id in selected_ids

            if redaction_box.is_repeat_draft:
                border_color, tip = (
                    "orange",
                    "Repeat Draft (click=select, right-click=options)",
                )
            else:
                border_color = "#000000"
                tip = "Standard Redaction (click=select, right-click=options)"

            box_content: ft.Text | None = None

            border_width = 4 if is_selected else 2
            if is_selected:
                border_color = "#00FF00"
                tip = f"SELECTED - {tip}"

            overlay = self._build_single_box_overlay(
                redaction_box,
                s,
                page_index,
                border_color,
                border_width,
                tip,
                box_content,
            )
            overlays.append(overlay)

        return overlays

    def _create_search_result_overlays(
        self, result: SearchResult, scale: float
    ) -> list[ft.Container]:
        """Create overlay containers for a single search result (handles multi-rectangle results)."""
        overlays: list[ft.Container] = []

        boxes_to_render = result.rects if result.rects else []

        if not boxes_to_render:
            return overlays

        for box in boxes_to_render:
            s = to_screen_rect(box, scale)

            def make_click_handler(
                res: SearchResult,
            ) -> Callable[[ft.ControlEvent], None]:
                def handler(e: ft.ControlEvent) -> None:
                    from src.ui.views import base_results_view

                    base_results_view.toggle_result_redaction_simple(res)

                return handler

            def make_right_click_handler(
                res: SearchResult,
            ) -> Callable[[ft.ControlEvent], None]:
                def handler(e: ft.ControlEvent) -> None:
                    if self.main_controller:
                        self.main_controller.search_results.dismiss_match(res)

                        self.page.open(
                            ft.SnackBar(
                                ft.Text(f"Dismissed: '{res.match}'"),
                                bgcolor="grey",
                                duration=1500,
                            )
                        )

                return handler

            overlays.append(
                ft.GestureDetector(
                    left=s.x,
                    top=s.y,
                    width=s.w,
                    height=s.h,
                    content=ft.Container(
                        width=s.w,
                        height=s.h,
                        bgcolor="#50FFFF00",
                        border=ft.border.all(1, "#FFA500"),
                        border_radius=2,
                        tooltip="Left-click: redact | Right-click: dismiss",
                    ),
                    on_tap=make_click_handler(result),
                    on_secondary_tap=make_right_click_handler(result),
                )
            )

        return overlays

    def _build_single_box_overlay(
        self,
        redaction_box: RedactionBox,
        s: ScreenBox,
        page_index: int,
        border_color: str,
        border_width: int,
        tip: str,
        box_content: ft.Text | None,
    ) -> ft.Container:
        box_selection_mode = redaction_box.selection_mode
        box_id = redaction_box.id

        resize_strip_width = 14
        corner_size = 30
        snap_edge_width = 24
        if box_selection_mode == "rectangle":
            inner_width = max(10, s.w - 2 * resize_strip_width)
            inner_height = max(10, s.h - 2 * resize_strip_width)
        else:
            inner_width = max(10, s.w - 2 * snap_edge_width)
            inner_height = s.h

        inner_content = ft.Container(
            width=inner_width,
            height=inner_height,
            bgcolor="#80808080",
            content=box_content,
            alignment=ft.alignment.center_left if box_content else None,
            padding=ft.padding.only(left=2) if box_content else None,
        )

        resize_regions = []

        if box_selection_mode == "rectangle":
            inner_detector = ft.GestureDetector(
                mouse_cursor=ft.MouseCursor.MOVE,
                content=inner_content,
                on_tap=lambda e, b=redaction_box: self.on_box_click(b, e),
                on_secondary_tap=lambda e, b=redaction_box: self.on_box_right_click(
                    b, e
                ),
                on_pan_start=lambda e, bid=box_id, p=page_index: self.on_box_edit_start(
                    bid, "move", p, e
                ),
                on_pan_update=lambda e: self.on_box_edit_update(e),
                on_pan_end=lambda e: self.on_box_edit_end(e),
            )
            resize_regions.append(
                ft.Container(
                    width=corner_size,
                    height=corner_size,
                    left=0,
                    top=0,
                    bgcolor="#80808080",
                    content=ft.GestureDetector(
                        content=ft.Container(width=corner_size, height=corner_size),
                        mouse_cursor=ft.MouseCursor.RESIZE_UP_LEFT,
                        on_pan_start=lambda e, bid=box_id, p=page_index, k="nw": self.on_box_edit_start(
                            bid, k, p, e
                        ),
                        on_pan_update=lambda e: self.on_box_edit_update(e),
                        on_pan_end=lambda e: self.on_box_edit_end(e),
                        on_secondary_tap=lambda e, b=redaction_box: self.on_box_right_click(
                            b, e
                        ),
                    ),
                )
            )

            resize_regions.append(
                ft.Container(
                    width=corner_size,
                    height=corner_size,
                    left=s.w - corner_size,
                    top=0,
                    bgcolor="#80808080",
                    content=ft.GestureDetector(
                        content=ft.Container(width=corner_size, height=corner_size),
                        mouse_cursor=ft.MouseCursor.RESIZE_UP_RIGHT,
                        on_pan_start=lambda e, bid=box_id, p=page_index, k="ne": self.on_box_edit_start(
                            bid, k, p, e
                        ),
                        on_pan_update=lambda e: self.on_box_edit_update(e),
                        on_pan_end=lambda e: self.on_box_edit_end(e),
                        on_secondary_tap=lambda e, b=redaction_box: self.on_box_right_click(
                            b, e
                        ),
                    ),
                )
            )

            resize_regions.append(
                ft.Container(
                    width=corner_size,
                    height=corner_size,
                    left=0,
                    top=s.h - corner_size,
                    bgcolor="#80808080",
                    content=ft.GestureDetector(
                        content=ft.Container(width=corner_size, height=corner_size),
                        mouse_cursor=ft.MouseCursor.RESIZE_DOWN_LEFT,
                        on_pan_start=lambda e, bid=box_id, p=page_index, k="sw": self.on_box_edit_start(
                            bid, k, p, e
                        ),
                        on_pan_update=lambda e: self.on_box_edit_update(e),
                        on_pan_end=lambda e: self.on_box_edit_end(e),
                        on_secondary_tap=lambda e, b=redaction_box: self.on_box_right_click(
                            b, e
                        ),
                    ),
                )
            )

            resize_regions.append(
                ft.Container(
                    width=corner_size,
                    height=corner_size,
                    left=s.w - corner_size,
                    top=s.h - corner_size,
                    bgcolor="#80808080",
                    content=ft.GestureDetector(
                        content=ft.Container(width=corner_size, height=corner_size),
                        mouse_cursor=ft.MouseCursor.RESIZE_DOWN_RIGHT,
                        on_pan_start=lambda e, bid=box_id, p=page_index, k="se": self.on_box_edit_start(
                            bid, k, p, e
                        ),
                        on_pan_update=lambda e: self.on_box_edit_update(e),
                        on_pan_end=lambda e: self.on_box_edit_end(e),
                        on_secondary_tap=lambda e, b=redaction_box: self.on_box_right_click(
                            b, e
                        ),
                    ),
                )
            )

            resize_regions.append(
                ft.Container(
                    width=s.w - 2 * corner_size,
                    height=resize_strip_width,
                    left=corner_size,
                    top=0,
                    bgcolor="#80808080",
                    content=ft.GestureDetector(
                        content=ft.Container(
                            width=s.w - 2 * corner_size,
                            height=resize_strip_width,
                        ),
                        mouse_cursor=ft.MouseCursor.RESIZE_UP_DOWN,
                        on_pan_start=lambda e, bid=box_id, p=page_index, k="n": self.on_box_edit_start(
                            bid, k, p, e
                        ),
                        on_pan_update=lambda e: self.on_box_edit_update(e),
                        on_pan_end=lambda e: self.on_box_edit_end(e),
                        on_secondary_tap=lambda e, b=redaction_box: self.on_box_right_click(
                            b, e
                        ),
                    ),
                )
            )

            resize_regions.append(
                ft.Container(
                    width=s.w - 2 * corner_size,
                    height=resize_strip_width,
                    left=corner_size,
                    top=s.h - resize_strip_width,
                    bgcolor="#80808080",
                    content=ft.GestureDetector(
                        content=ft.Container(
                            width=s.w - 2 * corner_size,
                            height=resize_strip_width,
                        ),
                        mouse_cursor=ft.MouseCursor.RESIZE_UP_DOWN,
                        on_pan_start=lambda e, bid=box_id, p=page_index, k="s": self.on_box_edit_start(
                            bid, k, p, e
                        ),
                        on_pan_update=lambda e: self.on_box_edit_update(e),
                        on_pan_end=lambda e: self.on_box_edit_end(e),
                        on_secondary_tap=lambda e, b=redaction_box: self.on_box_right_click(
                            b, e
                        ),
                    ),
                )
            )

            resize_regions.append(
                ft.Container(
                    width=resize_strip_width,
                    height=s.h - 2 * corner_size,
                    left=0,
                    top=corner_size,
                    bgcolor="#80808080",
                    content=ft.GestureDetector(
                        content=ft.Container(
                            width=resize_strip_width,
                            height=s.h - 2 * corner_size,
                        ),
                        mouse_cursor=ft.MouseCursor.RESIZE_LEFT_RIGHT,
                        on_pan_start=lambda e, bid=box_id, p=page_index, k="w": self.on_box_edit_start(
                            bid, k, p, e
                        ),
                        on_pan_update=lambda e: self.on_box_edit_update(e),
                        on_pan_end=lambda e: self.on_box_edit_end(e),
                        on_secondary_tap=lambda e, b=redaction_box: self.on_box_right_click(
                            b, e
                        ),
                    ),
                )
            )

            resize_regions.append(
                ft.Container(
                    width=resize_strip_width,
                    height=s.h - 2 * corner_size,
                    left=s.w - resize_strip_width,
                    top=corner_size,
                    bgcolor="#80808080",
                    content=ft.GestureDetector(
                        content=ft.Container(
                            width=resize_strip_width,
                            height=s.h - 2 * corner_size,
                        ),
                        mouse_cursor=ft.MouseCursor.RESIZE_LEFT_RIGHT,
                        on_pan_start=lambda e, bid=box_id, p=page_index, k="e": self.on_box_edit_start(
                            bid, k, p, e
                        ),
                        on_pan_update=lambda e: self.on_box_edit_update(e),
                        on_pan_end=lambda e: self.on_box_edit_end(e),
                        on_secondary_tap=lambda e, b=redaction_box: self.on_box_right_click(
                            b, e
                        ),
                    ),
                )
            )
        else:
            inner_detector = ft.GestureDetector(
                content=inner_content,
                on_tap=lambda e, b=redaction_box: self.on_box_click(b, e),
                on_secondary_tap=lambda e, b=redaction_box: self.on_box_right_click(
                    b, e
                ),
            )

            resize_regions.append(
                ft.Container(
                    width=snap_edge_width,
                    height=s.h,
                    left=0,
                    top=0,
                    bgcolor="#80808080",
                    content=ft.GestureDetector(
                        mouse_cursor=ft.MouseCursor.RESIZE_LEFT_RIGHT,
                        content=ft.Container(width=snap_edge_width, height=s.h),
                        on_pan_start=lambda e, bid=box_id, p=page_index, k="w": self.on_box_edit_start(
                            bid, k, p, e
                        ),
                        on_pan_update=lambda e: self.on_box_edit_update(e),
                        on_pan_end=lambda e: self.on_box_edit_end(e),
                        on_secondary_tap=lambda e, b=redaction_box: self.on_box_right_click(
                            b, e
                        ),
                    ),
                )
            )

            resize_regions.append(
                ft.Container(
                    width=snap_edge_width,
                    height=s.h,
                    left=s.w - snap_edge_width,
                    top=0,
                    bgcolor="#80808080",
                    content=ft.GestureDetector(
                        mouse_cursor=ft.MouseCursor.RESIZE_LEFT_RIGHT,
                        content=ft.Container(width=snap_edge_width, height=s.h),
                        on_pan_start=lambda e, bid=box_id, p=page_index, k="e": self.on_box_edit_start(
                            bid, k, p, e
                        ),
                        on_pan_update=lambda e: self.on_box_edit_update(e),
                        on_pan_end=lambda e: self.on_box_edit_end(e),
                        on_secondary_tap=lambda e, b=redaction_box: self.on_box_right_click(
                            b, e
                        ),
                    ),
                )
            )

        outer_box = ft.Container(
            width=s.w,
            height=s.h,
            border=ft.border.all(border_width, border_color),
            bgcolor="#00000000",
            tooltip=tip,
            content=ft.Stack(
                [
                    ft.Container(
                        content=inner_detector,
                        left=(
                            resize_strip_width
                            if box_selection_mode == "rectangle"
                            else snap_edge_width
                        ),
                        top=(
                            resize_strip_width
                            if box_selection_mode == "rectangle"
                            else 0
                        ),
                    ),
                    *resize_regions,
                ]
            ),
        )

        positioned = ft.Container(
            content=outer_box,
            left=s.x,
            top=s.y,
        )

        return positioned

    def refresh_page_overlays(self, page_index: int) -> None:
        """Rebuild overlays for a single page without re-rendering the PDF image."""
        page_stack = self.main_controller.viewer._get_page_stack(page_index)  # type: ignore[attr-defined]
        if not page_stack:
            self.main_controller.viewer._render_viewer()  # type: ignore[attr-defined]
            return

        fname = self.main_controller.state.viewer.file_name or ""
        for box in self.state.project.redactions.get(fname, {}).get(page_index, []):
            box_id = box.id
            if box_id in self._handle_controls:
                del self._handle_controls[box_id]

        scale = self.get_scale_for_page(page_index)

        if len(page_stack.controls) > 0:
            pdf_image = page_stack.controls[0]
            new_overlays = self.build_page_overlays(page_index, scale)
            page_stack.controls = [pdf_image] + new_overlays
            success = _safe_update(page_stack)
            if not success:
                self.main_controller.viewer._render_viewer()  # type: ignore[attr-defined]

    def get_scale_for_page(self, page_index: int) -> float:
        return float(
            self.main_controller.state.viewer.scale_factors.get(page_index, 1.0)
        )

    def on_box_click(self, redaction_box: RedactionBox, e: ft.ControlEvent) -> None:
        if hasattr(self.main_controller, "redaction_interaction"):
            add_to_selection = getattr(e, "ctrl", False) or getattr(e, "shift", False)
            self.main_controller.redaction_interaction.toggle_annotation_selection(  # type: ignore[attr-defined]
                redaction_box, add_to_selection
            )

    def on_box_right_click(
        self, redaction_box: RedactionBox, e: ft.ControlEvent
    ) -> None:
        if hasattr(self.main_controller, "redaction_interaction"):
            self.main_controller.redaction_interaction.on_box_right_click(  # type: ignore[attr-defined]
                redaction_box, e
            )

    def on_box_edit_start(
        self, box_id: str, kind: str, page_index: int, e: ft.DragStartEvent
    ) -> None:
        if hasattr(self.main_controller, "redaction_interaction"):
            self.main_controller.redaction_interaction.on_box_edit_start(  # type: ignore[attr-defined]
                box_id, kind, page_index, e
            )

    def on_box_edit_update(self, e: ft.DragUpdateEvent) -> None:
        if hasattr(self.main_controller, "redaction_interaction"):
            self.main_controller.redaction_interaction.on_box_edit_update(e)  # type: ignore[attr-defined]

    def on_box_edit_end(self, e: ft.DragEndEvent) -> None:
        if hasattr(self.main_controller, "redaction_interaction"):
            self.main_controller.redaction_interaction.on_box_edit_end(e)  # type: ignore[attr-defined]
