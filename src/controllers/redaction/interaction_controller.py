from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import flet as ft

from src.core.domain.pdf_coordinates import ScreenBox, to_pdf_rect, to_screen_rect
from src.core.domain.pdf_rendering import extract_text_under_rect
from src.core.state.app_state import AppState, PdfBox, RedactionBox, UndoEntry
from src.core.state.ui_state import refs

if TYPE_CHECKING:
    from src.controllers.main_controller import MainController
    from src.controllers.redaction.data_controller import RedactionDataController
    from src.controllers.redaction.rendering_controller import (
        RedactionRenderingController,
    )

logger = logging.getLogger(__name__)


def _safe_update(control: ft.Control | None) -> bool:
    if control is None:
        return False
    if getattr(control, "page", None) is not None:
        control.update()
        return True
    return False


class RedactionInteractionController:
    def __init__(
        self,
        main_controller: MainController,
        page: ft.Page,
        data_controller: RedactionDataController,
        rendering_controller: RedactionRenderingController,
    ) -> None:
        self.main_controller = main_controller
        self.page = page
        self.data = data_controller
        self.rendering = rendering_controller

    @property
    def state(self) -> AppState:
        return self.main_controller.state

    def _convert_draft_to_normal(self, draft_box: RedactionBox) -> None:
        fname = self.state.viewer.file_name
        pidx = self.state.viewer.page_index
        if not fname or pidx is None:
            return
        if (
            fname not in self.state.project.redactions
            or pidx not in self.state.project.redactions[fname]
        ):
            return

        for box in self.state.project.redactions[fname][pidx]:
            if box.id == draft_box.id:
                box.is_repeat_draft = False
                break

        self.main_controller.viewer._refresh_all_rendered_overlays()
        self.page.open(
            ft.SnackBar(
                ft.Text("Converted proposed redaction to normal redaction"),
                bgcolor="green",
                duration=1500,
            )
        )

    def toggle_annotation_selection(
        self, pdf_box: RedactionBox, add_to_selection: bool = False
    ) -> None:
        if pdf_box.is_repeat_draft:
            self._convert_draft_to_normal(pdf_box)
            return

        box_id = pdf_box.id
        selected = self.state.redaction.selected_annotation_ids

        if add_to_selection:
            if box_id in selected:
                selected.discard(box_id)
            else:
                selected.add(box_id)
        else:
            if box_id in selected and len(selected) == 1:
                selected.clear()
            else:
                selected = {box_id}

        self.state.redaction.selected_annotation_ids = selected
        self.main_controller.viewer._refresh_all_rendered_overlays()

    def select_all_annotations_on_page(self) -> None:
        selected: set[str] = set()
        for pdf_box in self.data.get_current_page_redactions():
            box_id = pdf_box.id
            if box_id:
                selected.add(box_id)
        self.state.redaction.selected_annotation_ids = selected
        self.main_controller.viewer._refresh_all_rendered_overlays()
        self.page.open(
            ft.SnackBar(
                ft.Text(f"Selected {len(selected)} annotations on page."),
                bgcolor="blue",
            )
        )

    def select_all_annotations_in_document(self) -> None:
        fname = self.state.viewer.file_name
        if not fname or fname not in self.state.project.redactions:
            return

        selected: set[str] = set()
        for page_idx, boxes in self.state.project.redactions[fname].items():
            for pdf_box in boxes:
                box_id = pdf_box.id
                if box_id:
                    selected.add(box_id)
        self.state.redaction.selected_annotation_ids = selected
        self.main_controller.viewer._refresh_all_rendered_overlays()
        self.page.open(
            ft.SnackBar(
                ft.Text(f"Selected {len(selected)} annotations in document."),
                bgcolor="blue",
            )
        )

    def clear_annotation_selection(self) -> None:
        self.state.redaction.selected_annotation_ids = set()
        page_idx = int(self.state.viewer.page_index)
        if file_path := self.state.viewer.file_path:
            self.main_controller.viewer.navigate_to_page(file_path, page_idx + 1)

    def delete_selected_annotations(self) -> None:
        selected = self.state.redaction.selected_annotation_ids
        if not selected:
            return

        fname = self.state.viewer.file_name
        if not fname or fname not in self.state.project.redactions:
            return

        if len(selected) > 5:
            dlg: ft.AlertDialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Confirm Delete"),
                content=ft.Text(f"Delete {len(selected)} annotations?"),
                actions=[],
            )

            def do_delete(_: ft.ControlEvent) -> None:
                dlg.open = False
                self.page.update()
                self._perform_bulk_delete(selected)

            def do_cancel(_: ft.ControlEvent) -> None:
                dlg.open = False
                self.page.update()

            dlg.actions = [
                ft.TextButton("Delete", on_click=do_delete),
                ft.TextButton("Cancel", on_click=do_cancel),
            ]
            self.page.overlay.append(dlg)
            dlg.open = True
            self.page.update()
        else:
            self._perform_bulk_delete(selected)

    def _perform_bulk_delete(self, selected_ids: set[str]) -> None:
        fname = self.state.viewer.file_name
        if not fname or fname not in self.state.project.redactions:
            return

        from dataclasses import replace

        from src.core.state.app_state import UndoActionRemoveBoxes

        removed_entries: list[UndoEntry] = []

        for p_idx in list(self.state.project.redactions[fname].keys()):
            old_list = self.state.project.redactions[fname][p_idx]
            kept: list[RedactionBox] = []
            for b in old_list:
                if b.id in selected_ids:
                    box_copy = replace(
                        b,
                        repeat_pages=list(b.repeat_pages),
                    )
                    removed_entries.append(
                        UndoEntry(
                            file_name=fname,
                            page_idx=p_idx,
                            box=box_copy,
                        )
                    )
                else:
                    kept.append(b)
            self.state.project.redactions[fname][p_idx] = kept

        if removed_entries:
            undo_action = UndoActionRemoveBoxes(
                action="remove_boxes", entries=removed_entries
            )
            self.data._push_undo(undo_action)
            self.state.redaction.selected_annotation_ids = set()
            self.main_controller.viewer._refresh_all_rendered_overlays()
            self.page.update()
            self.page.open(
                ft.SnackBar(
                    ft.Text(f"Deleted {len(removed_entries)} annotations."),
                    bgcolor="green",
                )
            )

    def _box_to_pdf_box(self, box: RedactionBox) -> PdfBox:
        return PdfBox(x=box.x, y=box.y, w=box.w, h=box.h)

    def on_box_edit_start(
        self, box_id: str, kind: str, page_index: int, e: ft.DragStartEvent
    ) -> None:
        fname = self.state.viewer.file_name or ""
        box: RedactionBox | None = None
        for b in self.state.project.redactions.get(fname, {}).get(page_index, []):
            if b.id == box_id:
                box = b
                break
        if box is None:
            return
        scale = self.rendering.get_scale_for_page(page_index)
        s = to_screen_rect(self._box_to_pdf_box(box), scale)
        self.main_controller._hover_box_id = box_id
        self.main_controller.drag_data.edit_box_id = box_id
        self.main_controller.drag_data.edit_kind = kind
        self.main_controller.drag_data.edit_page_index = page_index
        self.main_controller.drag_data.edit_scale = scale
        self.main_controller.drag_data.ex0 = s.x
        self.main_controller.drag_data.ey0 = s.y
        self.main_controller.drag_data.ew0 = s.w
        self.main_controller.drag_data.eh0 = s.h
        self.main_controller.drag_data.acc_dx = 0.0
        self.main_controller.drag_data.acc_dy = 0.0

        preview = ft.Container(
            left=s.x,
            top=s.y,
            width=s.w,
            height=s.h,
            bgcolor="#3000FF00",
            border=ft.border.all(2, "#00FF00"),
        )
        self.main_controller.drag_data.edit_preview = preview

        page_stack = self.main_controller.viewer._get_page_stack(page_index)
        if page_stack:
            page_stack.controls.append(preview)
            _safe_update(page_stack)

    def on_box_edit_update(self, e: ft.DragUpdateEvent) -> None:
        if (
            self.main_controller.drag_data.edit_box_id is None
            or not self.main_controller.drag_data.edit_preview
        ):
            return
        delta_x = getattr(e, "delta_x", 0.0)
        delta_y = getattr(e, "delta_y", 0.0)
        self.main_controller.drag_data.acc_dx += float(delta_x or 0.0)
        self.main_controller.drag_data.acc_dy += float(delta_y or 0.0)
        r = self._edit_screen_rect()
        preview = self.main_controller.drag_data.edit_preview
        preview.left = r.x
        preview.top = r.y
        preview.width = r.w
        preview.height = r.h
        _safe_update(preview)

    def on_box_edit_end(self, e: ft.DragEndEvent) -> None:
        if self.main_controller.drag_data.edit_box_id is None:
            return
        box_id = self.main_controller.drag_data.edit_box_id
        page_index = self.main_controller.drag_data.edit_page_index
        scale = self.main_controller.drag_data.edit_scale or 1.0
        fname = self.state.viewer.file_name or ""

        preview = self.main_controller.drag_data.edit_preview
        page_stack = self.main_controller.viewer._get_page_stack(page_index)
        if page_stack and preview and preview in page_stack.controls:
            page_stack.controls.remove(preview)

        final_screen = self._edit_screen_rect()
        before = to_pdf_rect(
            ScreenBox(
                x=self.main_controller.drag_data.ex0,
                y=self.main_controller.drag_data.ey0,
                w=self.main_controller.drag_data.ew0,
                h=self.main_controller.drag_data.eh0,
            ),
            scale,
        )
        after = to_pdf_rect(final_screen, scale)

        box: RedactionBox | None = None
        for b in self.state.project.redactions.get(fname, {}).get(page_index, []):
            if b.id == box_id:
                box = b
                break
        if box is not None and after != before:
            box.x = after.x
            box.y = after.y
            box.w = after.w
            box.h = after.h

            file_path = self.state.viewer.file_path
            if file_path and box.match is not None:
                updated_text = extract_text_under_rect(file_path, page_index, after)
                if updated_text:
                    box.match = updated_text

            from src.core.state.app_state import UndoActionEditBox

            old_box_snapshot = RedactionBox(
                id=box.id,
                x=before.x,
                y=before.y,
                w=before.w,
                h=before.h,
                page=box.page,
                selection_mode=box.selection_mode,
                match=box.match,
                term=box.term,
                batch_id=box.batch_id,
                is_repeat_draft=box.is_repeat_draft,
                repeat_pages=list(box.repeat_pages),
                section_title=box.section_title,
            )
            new_box_snapshot = RedactionBox(
                id=box.id,
                x=after.x,
                y=after.y,
                w=after.w,
                h=after.h,
                page=box.page,
                selection_mode=box.selection_mode,
                match=box.match,
                term=box.term,
                batch_id=box.batch_id,
                is_repeat_draft=box.is_repeat_draft,
                repeat_pages=list(box.repeat_pages),
                section_title=box.section_title,
            )
            undo_action = UndoActionEditBox(
                action="edit_box",
                file_name=fname,
                page_idx=page_index,
                old_box=old_box_snapshot,
                new_box=new_box_snapshot,
            )
            self.data._push_undo(undo_action)

        self.main_controller.drag_data.edit_box_id = None
        self.main_controller.drag_data.edit_kind = None
        self.main_controller.drag_data.edit_preview = None
        self.main_controller._hover_box_id = None

        col = refs.get("viewer_scroll_col")
        if col and col.current and 0 <= page_index < len(col.current.controls):
            self._remove_page_handles(page_index)
            col.current.controls[page_index] = (
                self.main_controller.viewer._render_page_stack(page_index)
            )
            _safe_update(col.current)

    def _edit_screen_rect(self) -> ScreenBox:
        x = self.main_controller.drag_data.ex0
        y = self.main_controller.drag_data.ey0
        w = self.main_controller.drag_data.ew0
        h = self.main_controller.drag_data.eh0
        dx = self.main_controller.drag_data.acc_dx
        dy = self.main_controller.drag_data.acc_dy
        kind = self.main_controller.drag_data.edit_kind or "move"
        min_sz = 6.0

        if kind == "move":
            x += dx
            y += dy
        else:
            if "n" in kind and h - dy >= min_sz:
                y = y + dy
                h = h - dy
            if "s" in kind and h + dy >= min_sz:
                h = h + dy
            if "w" in kind and w - dx >= min_sz:
                x = x + dx
                w = w - dx
            if "e" in kind and w + dx >= min_sz:
                w = w + dx
        return ScreenBox(x=x, y=y, w=w, h=h)

    def _remove_page_handles(self, page_index: int) -> None:
        fname = self.state.viewer.file_name or ""
        for box in self.state.project.redactions.get(fname, {}).get(page_index, []):
            box_id = box.id
            if box_id in self.main_controller._handle_controls:
                del self.main_controller._handle_controls[box_id]

    def on_box_right_click(self, pdf_box: RedactionBox, e: ft.ControlEvent) -> None:
        if pdf_box.batch_id:
            self.data.delete_batch(pdf_box.batch_id)
            self.page.open(
                ft.SnackBar(
                    ft.Text("Batch deleted (all related boxes)"),
                    bgcolor="grey",
                    duration=1000,
                )
            )
        else:
            self.data.remove_single_redaction(pdf_box)
            self.page.open(
                ft.SnackBar(
                    ft.Text("Redaction deleted"),
                    bgcolor="grey",
                    duration=1000,
                )
            )

    def set_mode(self, mode: str) -> None:
        self.main_controller.ui_gestures.set_mode(mode)
