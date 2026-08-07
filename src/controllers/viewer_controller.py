"""
viewer_controller.py - Handles PDF viewer rendering, navigation, zoom, and scroll
"""

from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING, Optional

import flet as ft

from src.core.domain.pdf_rendering import get_pdf_page_data
from src.core.state.app_state import AppState
from src.core.state.ui_state import refs
from src.ui.rendering import page_ui_builder

if TYPE_CHECKING:
    from src.controllers.main_controller import MainController


def _safe_update(control: ft.Control | None) -> bool:
    if control is None:
        return False
    try:
        if getattr(control, "page", None) is not None:
            control.update()
            return True
    except Exception:
        pass
    return False


class ViewerController:
    """Handles PDF viewer rendering, page navigation, zoom, and scroll."""

    def __init__(self, main_controller: MainController, page: ft.Page) -> None:
        self.main_controller = main_controller
        self.page = page
        self._page_heights: dict[int, float] = {}
        self._navigating_to_page: bool = False
        self._processing_scroll_event: bool = False
        self._debounce_timer: Optional[threading.Timer] = None
        self._last_scroll_data: Optional[dict[str, float]] = None

    @property
    def state(self) -> AppState:
        return self.main_controller.state

    def navigate_to_page(self, file_path: str, page_num: int) -> None:
        """
        UNIVERSAL ENTRY POINT for all page/navigation/rendering operations.

        Term filtering is read from state.search.current_term (set by dropdown).
        Category filtering is read from state.ui.current_tab (set by tab switch).
        """
        if not file_path:
            return

        self._navigating_to_page = True
        try:
            loading_overlay = refs.get("viewer_loading_overlay")
            if loading_overlay and loading_overlay.current:
                loading_overlay.current.visible = True
                with self.main_controller._page_update_lock:
                    self.page.update()

            page_idx = max(0, int(page_num) - 1)
            needs_file_load = self.state.viewer.file_path != file_path

            if needs_file_load:
                import fitz

                from src.core.state.app_state import BookmarkItem
                from src.ui.views import bookmarks_view, viewer_view

                with fitz.open(file_path) as doc:
                    toc = doc.get_toc(simple=True) or []
                    total_p = doc.page_count
                    self.state.viewer.total_pages = total_p

                    bms: list[BookmarkItem] = []
                    for i, item in enumerate(toc):
                        level, title, p_num = item[0], item[1], item[2]
                        end_p = toc[i + 1][2] - 1 if i < len(toc) - 1 else total_p
                        if end_p < p_num:
                            end_p = p_num
                        bms.append(
                            BookmarkItem(
                                level=level,
                                title=title,
                                page=p_num,
                                end_page=end_p,
                                file_path=file_path,
                                term="",
                            )
                        )
                    self.state.project.current_file_bookmarks = bms

                    self._page_heights.clear()
                    zoom = float(self.state.viewer.zoom)
                    for idx in range(total_p):
                        page = doc[idx]
                        page_height = page.rect.height * zoom
                        self._page_heights[idx] = page_height

            self.state.viewer.file_path = file_path
            self.state.viewer.file_name = os.path.basename(file_path)
            self.state.viewer.page_index = page_idx

            if self.state.ui.current_tab == "bookmarks":
                bookmarks_view.render_bookmarks_list("")

            if needs_file_load:
                if self.state.ui.current_tab == "viewer":
                    viewer_view.render_viewer_list("")

            # Reset scroll to 0 when switching files to prevent Flet from auto-clamping
            # old scroll position to new document bounds and generating stale scroll events
            if needs_file_load:
                col = refs.get("viewer_scroll_col")
                if col and col.current:
                    col.current.scroll_to(offset=0, duration=0)

            self._render_viewer(initial=needs_file_load)
            self._scroll_to_page(page_idx)
            self._refresh_all_rendered_overlays()

            if loading_overlay and loading_overlay.current:
                loading_overlay.current.visible = False
                self.page.update()
        finally:
            self._navigating_to_page = False

    def _refresh_all_rendered_overlays(self) -> None:
        col = refs.get("viewer_scroll_col")
        if not col or not col.current:
            return

        for page_idx, control in enumerate(col.current.controls):
            if self._is_placeholder(control):
                continue
            self.main_controller.redaction_rendering.refresh_page_overlays(page_idx)

        self._render_page_strip()

    def _is_placeholder(self, control: ft.Control) -> bool:
        return (
            isinstance(control, ft.Container)
            and isinstance(control.content, ft.Text)
            and control.content.value
            and control.content.value.startswith("Page ")
        )

    def _recalculate_page_heights_for_zoom(self) -> None:
        file_path: str | None = self.state.viewer.file_path
        if not file_path or not os.path.exists(file_path):
            return

        zoom: float = float(self.state.viewer.zoom)
        import fitz

        with fitz.open(file_path) as doc:
            for page_idx in range(doc.page_count):
                page = doc[page_idx]
                self._page_heights[page_idx] = page.rect.height * zoom

    def _render_page_strip(self) -> None:
        strip_row: ft.Ref[ft.Row] | None = refs.get("page_strip_row")
        if not strip_row or not strip_row.current:
            return

        total: int = int(self.state.viewer.total_pages)
        current_idx: int = int(self.state.viewer.page_index)

        if total <= 0:
            strip_row.current.controls = []
            _safe_update(strip_row.current)
            return

        fname: str | None = self.state.viewer.file_name
        from src.core.state.app_state import RedactionBox

        file_redactions: dict[int, list[RedactionBox]] = (
            self.state.project.redactions.get(fname, {}) if fname else {}
        )

        pages_with_matches: set[int] = page_ui_builder.get_pages_with_matches(
            self.state, fname
        )

        controls: list[ft.Control] = []
        for i in range(total):
            is_current: bool = i == current_idx
            has_gap: bool = (
                i in pages_with_matches and self.state.ui.current_tab == "consistency"
            )
            has_match: bool = (
                i in pages_with_matches and self.state.ui.current_tab != "consistency"
            )
            has_redactions: bool = i in file_redactions and len(file_redactions[i]) > 0

            from typing import Callable

            def make_click_handler(
                page_idx: int,
            ) -> Callable[[ft.ControlEvent], None]:
                return lambda e: self._page_strip_click(page_idx)

            click_handler: Callable[[ft.ControlEvent], None] = make_click_handler(i)

            page_item = page_ui_builder.build_page_strip_item(
                page_idx=i,
                is_current=is_current,
                has_gap=has_gap,
                has_match=has_match,
                has_redactions=has_redactions,
                redaction_count=len(file_redactions[i]) if has_redactions else 0,
                on_click_handler=click_handler,
            )
            controls.append(page_item)

        strip_row.current.controls = controls
        _safe_update(strip_row.current)

    def _page_strip_click(self, page_idx: int) -> None:
        file_path = self.state.viewer.file_path
        if not file_path:
            return
        self.navigate_to_page(file_path, page_idx + 1)

    def _render_viewer(self, initial: bool = False) -> None:
        col: ft.Ref[ft.Column] | None = refs.get("viewer_scroll_col")

        if not self.state.viewer.file_path:
            if col and col.current:
                col.current.controls.clear()
                self._page_heights.clear()
                self.main_controller.redaction_rendering._handle_controls.clear()
                self.page.update()
            return

        total: int = int(self.state.viewer.total_pages)
        if total == 0:
            return

        if not col or not col.current:
            return

        current_page: int = int(self.state.viewer.page_index)
        buffer: int = self.main_controller.config.ui.viewer_page_buffer
        start_page: int = max(0, current_page - buffer)
        end_page: int = min(total - 1, current_page + buffer)

        if initial or len(col.current.controls) != total:
            self.main_controller.redaction_rendering._handle_controls.clear()
            self._page_heights.clear()
            page_controls: list[ft.Control] = []
            for page_idx in range(total):
                if start_page <= page_idx <= end_page:
                    page_controls.append(self._render_page_stack(page_idx))
                else:
                    page_controls.append(self._create_placeholder(page_idx))
            col.current.controls = page_controls
        else:
            for page_idx in range(total):
                should_be_loaded: bool = start_page <= page_idx <= end_page
                current_control: ft.Control = col.current.controls[page_idx]

                is_placeholder: bool = (
                    isinstance(current_control, ft.Container)
                    and isinstance(current_control.content, ft.Text)
                    and current_control.content.value
                    and current_control.content.value.startswith("Page ")
                )

                if should_be_loaded and is_placeholder:
                    col.current.controls[page_idx] = self._render_page_stack(page_idx)
                elif not should_be_loaded and not is_placeholder:
                    self._remove_page_handles(page_idx)
                    col.current.controls[page_idx] = self._create_placeholder(page_idx)

        total_pages_lbl: ft.Text | None = refs["total_pages_lbl"].current
        if total_pages_lbl:
            total_pages_lbl.value = f"of {total}"
        page_num_txt: ft.TextField | None = refs["page_num_txt"].current
        if page_num_txt:
            page_num_txt.value = str(current_page + 1)

        self._render_page_strip()
        with self.main_controller._page_update_lock:
            self.page.update()

    def _remove_page_handles(self, page_idx: int) -> None:
        keys_to_remove: list[str] = [
            k
            for k in self.main_controller.redaction_rendering._handle_controls.keys()
            if k.startswith(f"{page_idx}_")
        ]
        for key in keys_to_remove:
            del self.main_controller.redaction_rendering._handle_controls[key]

    def _create_placeholder(self, page_idx: int) -> ft.Container:
        base_width: int = int(self.state.viewer.base_width)
        zoom: float = float(self.state.viewer.zoom)
        page_height: float | None = self._page_heights.get(page_idx)

        return page_ui_builder.build_page_placeholder(
            page_idx=page_idx,
            base_width=base_width,
            zoom=zoom,
            page_height=page_height,
            fallback_page_height=self.main_controller.config.ui.fallback_page_height,
        )

    def _render_page_stack(self, page_index: int) -> ft.Container:
        file_path: str | None = self.state.viewer.file_path
        if not file_path:
            return ft.Container(height=800, bgcolor="#F0F0F0")

        zoom: float = float(self.state.viewer.zoom)
        base_width: int = int(self.state.viewer.base_width)

        img_data: str | None
        scale: float
        w: float
        h: float
        total: int
        img_data, scale, w, h, total = get_pdf_page_data(
            file_path,
            page_index,
            zoom,
            base_width,
        )
        if img_data is None:
            return ft.Container(height=800, bgcolor="#F0F0F0")

        self.state.viewer.scale_factors[page_index] = scale
        self._page_heights[page_index] = h * scale

        pdf_image: ft.Image = page_ui_builder.build_pdf_page_image(
            img_data=img_data,
            width=w,
            height=h,
            scale=scale,
        )

        # Hover handler disabled for performance during initial load
        gesture_det: ft.GestureDetector = (
            page_ui_builder.build_pdf_page_gesture_detector(
                pdf_image=pdf_image,
                page_index=page_index,
                on_pan_start=self.main_controller.ui_gestures.on_pan_start,
                on_pan_update=self.main_controller.ui_gestures.on_pan_update,
                on_pan_end=self.main_controller.ui_gestures.on_pan_end,
                on_tap=self.main_controller.ui_gestures.on_page_tap,
                on_hover=None,
            )
        )

        controls: list[ft.Control] = [gesture_det]
        controls.extend(
            self.main_controller.redaction_rendering.build_page_overlays(
                page_index, scale
            )
        )

        return page_ui_builder.build_page_stack_container(
            controls=controls,
            width=w,
            height=h,
            scale=scale,
        )

    def _get_page_stack(self, page_index: int) -> ft.Stack | None:
        col: ft.Ref[ft.Column] | None = refs.get("viewer_scroll_col")
        if not col or not col.current:
            return None

        controls: list[ft.Control] = col.current.controls

        if page_index < 0 or page_index >= len(controls):
            return None

        container: ft.Control = controls[page_index]

        if hasattr(container, "content") and isinstance(container.content, ft.Stack):
            return container.content

        return None

    def _get_scale_for_page(self, page_index: int) -> float:
        return float(self.state.viewer.scale_factors.get(page_index, 1.0))

    def _scroll_to_page(self, page_idx: int) -> None:
        lock_was_held: bool = self._navigating_to_page
        if not lock_was_held:
            self._navigating_to_page = True

        col: ft.Ref[ft.Column] | None = refs.get("viewer_scroll_col")
        if col and col.current:
            spacing: int = self.main_controller.config.ui.viewer_scroll_spacing
            zoom: float = float(self.state.viewer.zoom)
            fallback_height: float = (
                self.main_controller.config.ui.fallback_page_height * zoom
            )

            scroll_offset: float = 0.0
            for idx in range(page_idx):
                page_height: float = self._page_heights.get(idx, fallback_height)
                scroll_offset += page_height + spacing

            col.current.scroll_to(offset=scroll_offset)
            _safe_update(col.current)

        self._scroll_page_strip_to_page(page_idx)

        if not lock_was_held:
            self._navigating_to_page = False

    def _scroll_page_strip_to_page(self, page_idx: int) -> None:
        strip_col: ft.Ref[ft.Column] | None = refs.get("page_strip_row")
        if not strip_col or not strip_col.current:
            return

        item_height: float = 22.0
        estimated_viewport_height: float = 500.0

        total_pages = int(self.state.viewer.total_pages)
        total_strip_height = total_pages * item_height
        max_scroll_offset = max(0.0, total_strip_height - estimated_viewport_height)

        center_offset: float = (
            (item_height * page_idx)
            - (estimated_viewport_height / 2.0)
            + (item_height / 2.0)
        )

        center_offset = max(0.0, min(center_offset, max_scroll_offset))

        strip_col.current.scroll_to(offset=center_offset)
        _safe_update(strip_col.current)

    def change_page(self, delta: int) -> None:
        file_path = self.state.viewer.file_path
        if not file_path:
            return
        total_pages: int = int(self.state.viewer.total_pages)
        new_idx: int = int(self.state.viewer.page_index) + int(delta)
        if 0 <= new_idx < total_pages:
            self.navigate_to_page(file_path, new_idx + 1)

    def go_to_page_direct(self, _: ft.ControlEvent) -> None:
        file_path = self.state.viewer.file_path
        if not file_path:
            return
        txt: ft.TextField | None = refs["page_num_txt"].current
        if not txt:
            return
        try:
            val: int = int(txt.value)
        except ValueError:
            return
        total_pages: int = int(self.state.viewer.total_pages)
        if 1 <= val <= total_pages:
            self.navigate_to_page(file_path, val)

    def change_zoom(self, delta: float) -> None:
        new_zoom: float = float(self.state.viewer.zoom) + float(delta)
        if 0.5 <= new_zoom <= 4.0:
            current_page_idx: int = int(self.state.viewer.page_index)

            self._navigating_to_page = True
            try:
                self.state.viewer.zoom = new_zoom
                zoom_lbl: ft.Text | None = refs["zoom_lbl"].current
                if zoom_lbl:
                    zoom_lbl.value = f"{int(new_zoom * 100)}%"
                    _safe_update(zoom_lbl)

                self._recalculate_page_heights_for_zoom()
                self._render_viewer(initial=True)
                self._scroll_to_page(current_page_idx)
            finally:
                self._navigating_to_page = False

    def _restore_ui_preferences(self) -> None:
        left_width: int | None = self.page.client_storage.get("left_panel_width")
        if left_width:
            self.state.viewer.left_panel_width = left_width
            left_col_ref: ft.Ref[ft.Column] | None = refs.get("left_col")
            if left_col_ref and left_col_ref.current:
                left_col_ref.current.width = left_width

        middle_width: int | None = self.page.client_storage.get("middle_panel_width")
        if middle_width:
            self.state.viewer.middle_panel_width = middle_width
            mid_col_ref: ft.Ref[ft.Column] | None = refs.get("mid_col")
            if mid_col_ref and mid_col_ref.current:
                mid_col_ref.current.width = middle_width

    def on_viewer_scroll(self, e: ft.ScrollEvent) -> None:
        if self.main_controller.ui_gestures.text_selection.is_active:
            self.main_controller.ui_gestures.text_selection.collapse()
            if self.state.viewer.page_index is not None:
                page_stack = self._get_page_stack(self.state.viewer.page_index)
                if page_stack:
                    self.main_controller.ui_gestures.selection_renderer.clear(
                        page_stack
                    )
                    try:
                        page_stack.update()
                    except Exception:
                        pass

        if self._navigating_to_page:
            return

        if self._processing_scroll_event:
            scroll_data = {
                "pixels": e.pixels,
                "viewport_dimension": (
                    e.viewport_dimension if e.viewport_dimension else 600
                ),
            }
            self._schedule_debounced_scroll(scroll_data)
            return

        self._processing_scroll_event = True
        try:
            scroll_data = {
                "pixels": e.pixels,
                "viewport_dimension": (
                    e.viewport_dimension if e.viewport_dimension else 600
                ),
            }

            self._process_scroll_event(scroll_data)
            self._schedule_debounced_scroll(scroll_data)
        finally:
            self._processing_scroll_event = False

    def _process_scroll_event(self, scroll_data: dict[str, float]) -> None:
        if self._navigating_to_page:
            return

        total_pages: int = int(self.state.viewer.total_pages)
        if total_pages == 0:
            return

        spacing: int = self.main_controller.config.ui.viewer_scroll_spacing
        viewport_height: float = scroll_data["viewport_dimension"]
        viewport_centerline: float = scroll_data["pixels"] + (viewport_height / 2)

        zoom: float = float(self.state.viewer.zoom)
        fallback_height: float = (
            self.main_controller.config.ui.fallback_page_height * zoom
        )

        cumulative_height: float = 0.0
        estimated_page: int = 0
        min_distance: float = float("inf")

        for page_idx in range(total_pages):
            page_height: float = self._page_heights.get(page_idx, fallback_height)

            page_top: float = cumulative_height
            page_center: float = page_top + (page_height / 2)

            distance: float = abs(page_center - viewport_centerline)

            if distance < min_distance:
                min_distance = distance
                estimated_page = page_idx

            cumulative_height += page_height + spacing

        estimated_page = max(0, min(total_pages - 1, estimated_page))

        current_page: int = int(self.state.viewer.page_index)
        buffer: int = self.main_controller.config.ui.viewer_page_buffer
        old_visible_start: int = max(0, current_page - buffer)
        old_visible_end: int = min(total_pages - 1, current_page + buffer)

        if estimated_page != current_page:
            self.state.viewer.page_index = estimated_page

            page_num_txt: ft.TextField | None = refs["page_num_txt"].current
            if page_num_txt:
                page_num_txt.value = str(estimated_page + 1)
                _safe_update(page_num_txt)

            self._scroll_page_strip_to_page(estimated_page)

            new_visible_start: int = max(0, estimated_page - buffer)
            new_visible_end: int = min(total_pages - 1, estimated_page + buffer)

            if (
                new_visible_start < old_visible_start
                or new_visible_end > old_visible_end
            ):
                self._render_viewer(initial=False)
            else:
                self._render_page_strip()

    def _schedule_debounced_scroll(self, scroll_data: dict[str, float]) -> None:
        """Ensures final scroll processing happens 500ms after scrolling stops."""
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()

        self._last_scroll_data = scroll_data

        self._debounce_timer = threading.Timer(0.5, self._debounced_scroll_callback)
        self._debounce_timer.daemon = True
        self._debounce_timer.start()

    def _debounced_scroll_callback(self) -> None:
        if self._last_scroll_data is None:
            return

        if self._navigating_to_page:
            return

        if self._processing_scroll_event:
            return

        self._processing_scroll_event = True
        try:
            self._process_scroll_event(self._last_scroll_data)
        finally:
            self._processing_scroll_event = False
            self._last_scroll_data = None
            self._debounce_timer = None
