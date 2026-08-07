from __future__ import annotations

import copy
import logging
from typing import cast

import flet as ft

from src.core.state.app_state import (
    AppState,
    RedactionBox,
    UndoAction,
    UndoActionRemoveBoxes,
    UndoActionEditBox,
    UndoEntry,
)
from src.core.state.ui_state import refs

logger = logging.getLogger(__name__)

_UNDO_LIMIT: int = 100


def _safe_update(control: ft.Control | None) -> bool:
    if control is None:
        return False
    if getattr(control, "page", None) is not None:
        control.update()
        return True
    return False


class RedactionDataController:
    def __init__(self, main_controller: "MainController", page: ft.Page) -> None:  # type: ignore[name-defined]
        self.main_controller = main_controller
        self.page = page

    @property
    def state(self) -> AppState:
        return cast(AppState, self.main_controller.state)

    def _push_undo(self, action: UndoAction) -> None:
        stack = self.state.project.undo_stack
        stack.append(action)
        if len(stack) > _UNDO_LIMIT:
            self.state.project.undo_stack = stack[-_UNDO_LIMIT:]
        self.state.project.redo_stack.clear()
        self._update_undo_label()

    def _update_undo_label(self) -> None:
        u = len(self.state.project.undo_stack)
        r = len(self.state.project.redo_stack)

        lbl = refs.get("undo_redo_label")
        if lbl and lbl.current:
            lbl.current.value = f"U:{u} R:{r}" if (u or r) else ""
            _safe_update(lbl.current)

        btn_undo = refs.get("btn_undo")
        if btn_undo and btn_undo.current:
            btn_undo.current.disabled = u == 0
            _safe_update(btn_undo.current)

        btn_redo = refs.get("btn_redo")
        if btn_redo and btn_redo.current:
            btn_redo.current.disabled = r == 0
            _safe_update(btn_redo.current)

    def _apply_action(self, action: UndoAction, reverse: bool = False) -> None:
        if isinstance(action, UndoActionRemoveBoxes):
            entries = action.entries
            if (action.action == "add_boxes" and not reverse) or (
                action.action == "remove_boxes" and reverse
            ):
                for e in entries:
                    fn = e.file_name
                    pi = e.page_idx
                    box = e.box
                    self.state.project.redactions.setdefault(fn, {}).setdefault(
                        pi, []
                    ).append(box)
            elif (action.action == "remove_boxes" and not reverse) or (
                action.action == "add_boxes" and reverse
            ):
                for e in entries:
                    fn = e.file_name
                    pi = e.page_idx
                    box = e.box
                    box_id = box.id
                    if (
                        fn in self.state.project.redactions
                        and pi in self.state.project.redactions[fn]
                    ):
                        self.state.project.redactions[fn][pi] = [
                            b
                            for b in self.state.project.redactions[fn][pi]
                            if b.id != box_id
                        ]
        elif isinstance(action, UndoActionEditBox):
            fn, pi = action.file_name, action.page_idx
            target_box = action.old_box if reverse else action.new_box
            source_id = action.new_box.id if reverse else action.old_box.id
            for b in self.state.project.redactions.get(fn, {}).get(pi, []):
                if b.id == source_id:
                    b.x = target_box.x
                    b.y = target_box.y
                    b.w = target_box.w
                    b.h = target_box.h
                    break

    def undo(self) -> None:
        stack = self.state.project.undo_stack
        if not stack:
            return
        action = stack.pop()
        self._apply_action(action, reverse=True)
        self.state.project.redo_stack.append(action)
        self._update_undo_label()
        self.main_controller.viewer._render_viewer(initial=True)

    def redo(self) -> None:
        stack = self.state.project.redo_stack
        if not stack:
            return
        action = stack.pop()
        self._apply_action(action, reverse=False)
        self.state.project.undo_stack.append(action)
        self._update_undo_label()
        self.main_controller.viewer._render_viewer(initial=True)

    def get_current_page_redactions(self) -> list[RedactionBox]:
        fname = self.state.viewer.file_name
        pidx = self.state.viewer.page_index
        if not fname or pidx is None:
            return []
        if (
            fname in self.state.project.redactions
            and pidx in self.state.project.redactions[fname]
        ):
            boxes: list[RedactionBox] = self.state.project.redactions[fname][pidx]
            return boxes
        return []

    def _add_redaction_raw(
        self, pdf_box: RedactionBox, page_idx: int, file_name: str | None = None
    ) -> None:
        fname = file_name or self.state.viewer.file_name
        if not fname:
            return
        self.state.project.redactions.setdefault(fname, {}).setdefault(
            page_idx, []
        ).append(pdf_box)

    def add_redaction_internal(
        self, pdf_box: RedactionBox, page_idx: int, file_name: str | None = None
    ) -> None:
        fname = file_name or self.state.viewer.file_name
        if not fname:
            return
        self._add_redaction_raw(pdf_box, page_idx, fname)
        self._push_undo(
            UndoActionRemoveBoxes(
                action="add_boxes",
                entries=[
                    UndoEntry(
                        file_name=fname,
                        page_idx=page_idx,
                        box=copy.deepcopy(pdf_box),
                    )
                ],
            )
        )

    def add_redaction_batch(
        self,
        pdf_boxes: list[RedactionBox],
        page_idx: int,
        file_name: str | None = None,
    ) -> None:
        fname = file_name or self.state.viewer.file_name
        if not fname:
            return

        for box in pdf_boxes:
            self._add_redaction_raw(box, page_idx, fname)

        entries: list[UndoEntry] = [
            UndoEntry(
                file_name=fname,
                page_idx=page_idx,
                box=copy.deepcopy(box),
            )
            for box in pdf_boxes
        ]
        self._push_undo(UndoActionRemoveBoxes(action="add_boxes", entries=entries))

    def remove_single_redaction(self, pdf_box: RedactionBox) -> None:
        fname = self.state.viewer.file_name
        pidx = self.state.viewer.page_index
        if not fname or pidx is None:
            return
        if (
            fname in self.state.project.redactions
            and pidx in self.state.project.redactions[fname]
        ):
            current_list = self.state.project.redactions[fname][pidx]
            target = None
            for b in current_list:
                if b.id == pdf_box.id:
                    target = b
                    break
            if target:
                batch_id_to_clear = target.batch_id if target.batch_id else None

                current_list.remove(target)
                self._push_undo(
                    UndoActionRemoveBoxes(
                        action="remove_boxes",
                        entries=[
                            UndoEntry(
                                file_name=fname,
                                page_idx=pidx,
                                box=copy.deepcopy(target),
                            )
                        ],
                    )
                )

                if batch_id_to_clear:
                    self._update_gap_state_after_deletion(batch_id_to_clear)
                    self._update_search_results_after_deletion(batch_id_to_clear)

                if target.pd_check_result:
                    self._refresh_pd_checker_results()

                self.main_controller.viewer._refresh_all_rendered_overlays()

    def _update_gap_state_after_deletion(self, batch_id: str) -> None:
        from src.core.state.app_state import ResultCategory

        for result in self.state.search.all_search_results:
            if result.category == ResultCategory.GAP and result.batch_id == batch_id:
                result.batch_id = ""
                result.redacted = False

                if self.state.ui.current_tab == "consistency":
                    from src.ui.views import consistency_view

                    consistency_view.render_consistency_list("")

                return

    def _update_search_results_after_deletion(self, batch_id: str) -> None:
        updated = False
        for result in self.state.search.all_search_results:
            if result.batch_id == batch_id:
                result.batch_id = ""
                result.redacted = False
                updated = True

        if updated and self.state.ui.current_tab == "matches":
            from src.core.state.ui_state import refs
            from src.ui.views import matches_view

            if refs.get("results_list") and refs["results_list"].current:
                matches_view.render_text_results_list(
                    refs["results_list"].current.data or ""
                )
        elif updated and self.state.ui.current_tab == "dose":
            from src.core.state.ui_state import refs
            from src.ui.views import dose_view

            if refs.get("dose_results_list") and refs["dose_results_list"].current:
                dose_view.render_dose_results_list(
                    refs["dose_results_list"].current.data or ""
                )
        elif updated and self.state.ui.current_tab == "ai_detect":
            from src.ui.views import ai_detection_view

            ai_detection_view.render_ai_detections_list()

    def _refresh_pd_checker_results(self) -> None:
        from src.ui.views import pd_checker_view

        pd_checker_view.refresh_pd_checker_results()

    def remove_batch_redaction(self, fname: str, batch_id: str) -> None:
        if not fname or fname not in self.state.project.redactions:
            return
        removed_entries: list[UndoEntry] = []
        had_pd_result = False
        for p_idx in list(self.state.project.redactions[fname].keys()):
            old_list = self.state.project.redactions[fname][p_idx]
            kept = []
            for b in old_list:
                if b.batch_id == batch_id:
                    removed_entries.append(
                        UndoEntry(
                            file_name=fname,
                            page_idx=p_idx,
                            box=copy.deepcopy(b),
                        )
                    )
                    if b.pd_check_result and not had_pd_result:
                        had_pd_result = True
                else:
                    kept.append(b)
            self.state.project.redactions[fname][p_idx] = kept
        if removed_entries:
            self._push_undo(
                UndoActionRemoveBoxes(action="remove_boxes", entries=removed_entries)
            )
            if had_pd_result:
                self._refresh_pd_checker_results()

    def remove_redaction_by_id(self, fname: str, box_id: str) -> None:
        if not fname or fname not in self.state.project.redactions:
            return
        removed_entry: UndoEntry | None = None
        had_pd_result = False
        for p_idx in list(self.state.project.redactions[fname].keys()):
            old_list = self.state.project.redactions[fname][p_idx]
            for i, b in enumerate(old_list):
                if b.id == box_id:
                    removed_entry = UndoEntry(
                        file_name=fname,
                        page_idx=p_idx,
                        box=copy.deepcopy(b),
                    )
                    if b.pd_check_result:
                        had_pd_result = True
                    old_list.pop(i)
                    break
            if removed_entry:
                break
        if removed_entry:
            self._push_undo(
                UndoActionRemoveBoxes(action="remove_boxes", entries=[removed_entry])
            )
            if had_pd_result:
                self._refresh_pd_checker_results()

    def select_batch(self, batch_id: str) -> None:
        file_name = self.state.viewer.file_name
        if not file_name or file_name not in self.state.project.redactions:
            return

        self.state.redaction.selected_annotation_ids = set()

        for page_idx, boxes in self.state.project.redactions[file_name].items():
            for box in boxes:
                if box.batch_id == batch_id:
                    self.state.redaction.selected_annotation_ids.add(box.id)

        self.main_controller.viewer._refresh_all_rendered_overlays()

    def delete_batch(self, batch_id: str) -> None:
        file_name = self.state.viewer.file_name
        if not file_name or file_name not in self.state.project.redactions:
            return

        deleted_count = 0
        pages_to_refresh: set[int] = set()
        removed_entries: list[UndoEntry] = []

        for page_idx, boxes in list(self.state.project.redactions[file_name].items()):
            boxes_to_keep = []
            for box in boxes:
                if box.batch_id == batch_id:
                    deleted_count += 1
                    pages_to_refresh.add(page_idx)
                    removed_entries.append(
                        UndoEntry(
                            file_name=file_name,
                            page_idx=page_idx,
                            box=copy.deepcopy(box),
                        )
                    )
                else:
                    boxes_to_keep.append(box)

            self.state.project.redactions[file_name][page_idx] = boxes_to_keep

        if removed_entries:
            self._push_undo(
                UndoActionRemoveBoxes(action="remove_boxes", entries=removed_entries)
            )

            self._update_gap_state_after_deletion(batch_id)
            self._update_search_results_after_deletion(batch_id)

            had_pd_result = any(entry.box.pd_check_result for entry in removed_entries)
            if had_pd_result:
                self._refresh_pd_checker_results()

        if self.state.viewer.file_path:
            self.main_controller.viewer.navigate_to_page(
                self.state.viewer.file_path, self.state.viewer.page_index + 1
            )

        if self.state.ui.current_tab == "matches":
            from src.ui.views import matches_view

            current_filter = refs.get("results_list")
            filter_text = (
                current_filter.current.data
                if current_filter and current_filter.current
                else ""
            )
            matches_view.render_text_results_list(filter_text)
        elif self.state.ui.current_tab == "dose":
            from src.ui.views import dose_view

            dose_filter = refs.get("dose_results_list")
            filter_text = (
                dose_filter.current.data if dose_filter and dose_filter.current else ""
            )
            dose_view.render_dose_results_list(filter_text)

        self.page.open(
            ft.SnackBar(
                ft.Text(f"Deleted {deleted_count} redactions"),
                bgcolor="grey",
                duration=1000,
            )
        )
