from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import flet as ft

import src.ui.dialogs as ui_dialogs
from src.core.state.app_state import RedactionBox, SelectionMode
from src.core.domain.pdf_coordinates import ScreenBox
from src.core.state.selection_state import TextSelection
from src.interaction import text_selection_mode
from src.interaction import refact_text_selection
from src.ui.rendering.selection_renderer import SelectionRenderer
from src.core.state.ui_state import refs

if TYPE_CHECKING:
    from src.controllers.main_controller import MainController


def _safe_update(control: ft.Control | None) -> bool:
    if control is None:
        return False
    if getattr(control, "page", None) is not None:
        control.update()
        return True
    return False


class UIGesturesController:
    def __init__(self, main_controller: MainController, page: ft.Page) -> None:
        self.main_controller = main_controller
        self.page = page
        self.text_selection = TextSelection()
        self.selection_renderer = SelectionRenderer()

    def set_mode(self, mode: str) -> None:
        """Maps unified interaction mode to internal state.

        rect_single      → drawing_mode=normal,  selection_mode=rectangle
        rect_repeat      → drawing_mode=repeat,  selection_mode=rectangle
        highlight_redact → drawing_mode=normal,  selection_mode=highlight_redact
        highlight_only   → drawing_mode=normal,  selection_mode=highlight_only
        """
        _MODES = ("rect_single", "rect_repeat", "highlight_redact", "highlight_only")
        if mode not in _MODES:
            raise ValueError(f"Unsupported mode: {mode}")

        rdx = self.main_controller.state.redaction
        rdx.drawing_mode = "repeat" if mode == "rect_repeat" else "normal"
        if mode == "highlight_redact":
            rdx.selection_mode = "highlight_redact"
        elif mode == "highlight_only":
            rdx.selection_mode = "highlight_only"
        else:
            rdx.selection_mode = "rectangle"

        self.page.client_storage.set("ui_mode", mode)

        for m in _MODES:
            btn = refs[f"btn_mode_{m}"].current
            if btn:
                btn.icon_color = "blue" if m == mode else "grey"

        if rdx.selection_mode == "rectangle":
            rdx.selected_annotation_ids = set()
        else:
            self.text_selection.collapse()
            self._update_selection_rendering(
                self.main_controller.state.viewer.page_index
            )

        if file_path := self.main_controller.state.viewer.file_path:
            self.main_controller.viewer.navigate_to_page(
                file_path, self.main_controller.state.viewer.page_index + 1
            )
        self.page.update()

    def _update_selection_rendering(self, page_index: int) -> None:
        page_stack = self.main_controller.viewer._get_page_stack(page_index)
        if not page_stack:
            return

        scale = self.main_controller.viewer._get_scale_for_page(page_index)
        self.selection_renderer.update_rendering(self.text_selection, page_stack, scale)

    def on_pan_start(self, e: ft.DragStartEvent, page_index: int = 0) -> None:
        sel_mode = self.main_controller.state.redaction.selection_mode
        if sel_mode in ("highlight_redact", "highlight_only"):
            refact_text_selection.handle_pan_start(
                e, page_index, self.text_selection, self.main_controller.state.viewer
            )
            return

        self.main_controller.drag_data.start_x = float(e.local_x)
        self.main_controller.drag_data.start_y = float(e.local_y)
        self.main_controller.drag_data.page_index = page_index

        if self.main_controller.state.redaction.drawing_mode != "normal":
            color = "orange"
            bgcolor = "#30FFA500"
        else:
            color = "#000000"
            bgcolor = "#30000000"

        self.main_controller.drag_data.box = ft.Container(
            left=self.main_controller.drag_data.start_x,
            top=self.main_controller.drag_data.start_y,
            width=0,
            height=0,
            border=ft.border.all(2, color),
            bgcolor=bgcolor,
        )

        page_stack = self.main_controller.viewer._get_page_stack(page_index)
        if page_stack:
            page_stack.controls.append(self.main_controller.drag_data.box)
            _safe_update(page_stack)

    def on_pan_update(self, e: ft.DragUpdateEvent, page_index: int = 0) -> None:
        sel_mode = self.main_controller.state.redaction.selection_mode
        if sel_mode in ("highlight_redact", "highlight_only"):
            refact_text_selection.handle_pan_update(
                e, page_index, self.text_selection, self.main_controller.state.viewer
            )
            self._update_selection_rendering(page_index)
            return

        if not self.main_controller.drag_data.box:
            return
        curr_x, curr_y = float(e.local_x), float(e.local_y)

        self.main_controller.drag_data.box.width = abs(
            curr_x - self.main_controller.drag_data.start_x
        )
        self.main_controller.drag_data.box.height = abs(
            curr_y - self.main_controller.drag_data.start_y
        )
        self.main_controller.drag_data.box.left = min(
            self.main_controller.drag_data.start_x, curr_x
        )
        self.main_controller.drag_data.box.top = min(
            self.main_controller.drag_data.start_y, curr_y
        )

        _safe_update(self.main_controller.drag_data.box)

    def on_pan_end(self, e: ft.DragEndEvent, page_index: int = 0) -> None:
        sel_mode = self.main_controller.state.redaction.selection_mode
        if sel_mode == "highlight_redact":
            text_selection_mode.handle_pan_end_redact(
                e, page_index, self.text_selection, self.main_controller  # type: ignore[arg-type]
            )
            self._update_selection_rendering(page_index)
            return
        elif sel_mode == "highlight_only":
            text_selection_mode.handle_pan_end_highlight_only(
                e, page_index, self.text_selection, self.main_controller  # type: ignore[arg-type]
            )
            self._update_selection_rendering(page_index)
            return

        if not self.main_controller.drag_data.box:
            return
        created_box: RedactionBox | None = None
        box_ctl = self.main_controller.drag_data.box
        if float(box_ctl.width) > 5 and float(box_ctl.height) > 5:
            screen_x = float(box_ctl.left)
            screen_y = float(box_ctl.top)
            screen_w = float(box_ctl.width)
            screen_h = float(box_ctl.height)

            page_idx = self.main_controller.drag_data.page_index
            scale = self.main_controller.viewer._get_scale_for_page(page_idx)

            pdf_x = screen_x / scale
            pdf_y = screen_y / scale
            pdf_w = screen_w / scale
            pdf_h = screen_h / scale

            box_id = str(uuid.uuid4())
            is_repeat_draft = (
                self.main_controller.state.redaction.drawing_mode == "repeat"
            )

            match_text: str | None = None
            file_path = self.main_controller.state.viewer.file_path
            if file_path:
                from src.core.domain.pdf_rendering import extract_text_under_rect
                from src.core.state.app_state import PdfBox

                pdf_box = PdfBox(x=pdf_x, y=pdf_y, w=pdf_w, h=pdf_h)
                match_text = extract_text_under_rect(file_path, page_idx, pdf_box)

            section_title: str | None = None
            if file_path:
                from src.core.domain.toc_util import get_section_title_for_page

                section_title = get_section_title_for_page(file_path, page_idx + 1)

            created_box = RedactionBox(
                id=box_id,
                x=pdf_x,
                y=pdf_y,
                w=pdf_w,
                h=pdf_h,
                page=page_idx,
                selection_mode=SelectionMode.RECTANGLE,
                match=match_text,
                is_repeat_draft=is_repeat_draft,
                section_title=section_title,
            )

            self.main_controller.redaction_data.add_redaction_internal(
                created_box, page_idx
            )

        page_stack = self.main_controller.viewer._get_page_stack(
            self.main_controller.drag_data.page_index
        )
        if page_stack and box_ctl in page_stack.controls:
            page_stack.controls.remove(box_ctl)

        self.main_controller.drag_data.box = None

        if created_box and page_stack:
            scale = self.main_controller.viewer._get_scale_for_page(
                self.main_controller.drag_data.page_index
            )
            screen_box = ScreenBox(
                x=created_box.x * scale,
                y=created_box.y * scale,
                w=created_box.w * scale,
                h=created_box.h * scale,
            )

            border_color = "#000000"
            tip = "Standard Redaction (click=select, right-click=options)"
            border_width = 2
            box_content = None

            overlay = (
                self.main_controller.redaction_rendering._build_single_box_overlay(
                    created_box,
                    screen_box,
                    self.main_controller.drag_data.page_index,
                    border_color,
                    border_width,
                    tip,
                    box_content,
                )
            )
            page_stack.controls.append(overlay)
            _safe_update(page_stack)

        if created_box and created_box.is_repeat_draft:
            ui_dialogs.show_repeat_dialog(
                controller=self.main_controller, draft_box=created_box
            )

    def on_page_tap(self, e: ft.ControlEvent) -> None:
        pass
