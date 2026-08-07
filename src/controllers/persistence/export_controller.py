from __future__ import annotations

import copy
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

from src.core.domain.pdf_rendering import batch_save_redacted_pdfs
from src.core.domain.excel_export import (
    save_results_to_excel,
    export_terms_to_excel,
    import_terms_from_excel,
)
from src.core.state.app_state import PdfBox, RedactionBox, SearchResult, TermItem
from src.core.state.ui_state import refs

if TYPE_CHECKING:
    from src.controllers.main_controller import MainController

logger = logging.getLogger(__name__)


class ExportController:
    def __init__(self, main_controller: MainController, page: ft.Page) -> None:
        self.main_controller = main_controller
        self.page = page
        self._batch_save_folder_picker: ft.FilePicker = ft.FilePicker(
            on_result=self._on_batch_save_folder_result
        )

    def batch_save_all_pdfs(self, _: ft.ControlEvent | None = None) -> None:
        if self.main_controller.state.search.search_running:
            self.page.open(
                ft.SnackBar(
                    ft.Text("A search is running. Please wait."), bgcolor="orange"
                )
            )
            return

        pending = self.get_files_with_pending_redactions()
        if not pending:
            self.page.open(
                ft.SnackBar(
                    ft.Text("No files have pending redactions."), bgcolor="grey"
                )
            )
            return

        path_map = self._build_file_path_map()

        missing = [f for f in pending if f not in path_map]
        if missing:
            names = ", ".join(missing[:5])
            suffix = f" and {len(missing) - 5} more" if len(missing) > 5 else ""
            self.page.open(
                ft.SnackBar(
                    ft.Text(f"Cannot resolve paths for: {names}{suffix}"),
                    bgcolor="orange",
                )
            )

        saveable = [f for f in pending if f in path_map]
        if not saveable:
            self.page.open(
                ft.SnackBar(ft.Text("No saveable files found."), bgcolor="red")
            )
            return

        self._pending_batch_save = (path_map, saveable)
        self._batch_save_folder_picker.get_directory_path(
            dialog_title="Select destination folder for redacted PDFs"
        )

    def _on_batch_save_folder_result(self, e: ft.FilePickerResultEvent) -> None:
        if not e.path:
            return

        output_dir = str(e.path)

        if not hasattr(self, "_pending_batch_save"):
            return

        path_map, saveable = self._pending_batch_save
        del self._pending_batch_save

        self.main_controller.state.project.batch_save_status = {
            f: "saving" for f in saveable
        }

        from src.ui.views import files_view

        files_view.render_file_list()

        if refs.get("search_status") and refs["search_status"].current:
            refs["search_status"].current.value = (
                f"Batch saving {len(saveable)} file(s)..."
            )
        if refs.get("search_progress") and refs["search_progress"].current:
            refs["search_progress"].current.visible = True
            refs["search_progress"].current.value = 0
        self.page.update()

        thread = threading.Thread(
            target=self._batch_save_worker,
            args=(path_map, output_dir),
            daemon=True,
        )
        thread.start()

    def _batch_save_worker(
        self, path_map: dict[str, str], output_dir: str | None = None
    ) -> None:
        redactions_snapshot = copy.deepcopy(
            dict(self.main_controller.state.project.redactions)
        )
        toc_snapshot = copy.deepcopy(
            dict(self.main_controller.state.project.toc_redactions)
        )

        converted_redactions: dict[str, dict[int, list[PdfBox]]] = {}
        for fname, pages in redactions_snapshot.items():
            converted_redactions[fname] = {}
            for page_idx, boxes in pages.items():
                converted_redactions[fname][page_idx] = [
                    PdfBox(x=box.x, y=box.y, w=box.w, h=box.h) for box in boxes
                ]

        save_start = time.monotonic()

        def _progress(
            completed: int, total: int, fname: str, success: bool, detail: str
        ) -> None:
            status = "saved" if success else f"error:{detail}"
            self.main_controller.state.project.batch_save_status[fname] = status

            if refs.get("search_progress") and refs["search_progress"].current:
                refs["search_progress"].current.value = (
                    completed / total if total else 0
                )
            if refs.get("search_status") and refs["search_status"].current:
                icon = "✓" if success else "✗"
                refs["search_status"].current.value = (
                    f"Batch save: {completed}/{total} — {icon} {fname}"
                )
            self.page.update()

        results = batch_save_redacted_pdfs(
            all_redactions=converted_redactions,
            all_toc_redactions=toc_snapshot,
            file_path_map=path_map,
            progress_callback=_progress,
            output_dir=output_dir,
        )

        elapsed = time.monotonic() - save_start
        success_count = sum(1 for r in results if r.success)
        fail_count = sum(1 for r in results if not r.success)

        if refs.get("search_progress") and refs["search_progress"].current:
            refs["search_progress"].current.visible = False
        if refs.get("search_status") and refs["search_status"].current:
            msg = f"Batch save complete: {success_count} saved"
            if fail_count:
                msg += f", {fail_count} failed"
            msg += f" in {elapsed:.1f}s"
            refs["search_status"].current.value = msg

        from src.ui.views import files_view

        files_view.render_file_list()

        color = "green" if fail_count == 0 else "orange"
        self.page.open(
            ft.SnackBar(
                ft.Text(
                    f"Batch save: {success_count} saved, {fail_count} failed ({elapsed:.1f}s)"
                ),
                bgcolor=color,
            )
        )

        if fail_count > 0:
            error_lines = []
            for r in results:
                if not r.success:
                    error_lines.append(
                        f"  • {r.file_name}: {r.error if r.error else 'Unknown'}"
                    )
            logger.warning("Batch save failures:\n" + "\n".join(error_lines))

            error_summary = "\n".join(
                f"• {r.file_name}: {r.error if r.error else 'Unknown'}"
                for r in results
                if not r.success
            )

            def close_dialog(_e: ft.ControlEvent) -> None:
                error_dlg.open = False
                self.page.update()

            error_dlg: ft.AlertDialog = ft.AlertDialog(
                title=ft.Text("Batch Save Errors"),
                content=ft.Column(
                    [
                        ft.Text(
                            f"{fail_count} file(s) failed to save:",
                            weight="bold",
                            color="red",
                        ),
                        ft.Text(
                            error_summary,
                            size=12,
                            selectable=True,
                        ),
                    ],
                    tight=True,
                    spacing=10,
                    scroll=ft.ScrollMode.AUTO,
                    height=300,
                ),
                actions=[
                    ft.FilledButton("OK", on_click=close_dialog),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            self.page.open(error_dlg)

        self.page.update()

    def export_results_to_excel(self, _: ft.ControlEvent) -> None:
        folder = self.page.client_storage.get("pdf_folder")
        if not folder:
            self.page.open(ft.SnackBar(ft.Text("No folder selected."), bgcolor="grey"))
            return
        results = self._get_filtered_results_for_export()
        if not results:
            self.page.open(
                ft.SnackBar(
                    ft.Text("No results to export (current filters)."), bgcolor="grey"
                )
            )
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = Path(folder) / f"RapidRedact_Results_{ts}.xlsx"
        rows: list[dict[str, str | int]] = []
        for r in results:
            rows.append(
                {
                    "file_name": r.file_name,
                    "page": r.page,
                    "term": r.term,
                    "match": r.match,
                    "context": r.context,
                }
            )
        ok = save_results_to_excel(rows, str(out_path))
        if not ok:
            self.page.open(ft.SnackBar(ft.Text("Excel export failed."), bgcolor="red"))
            return
        self.page.open(
            ft.SnackBar(ft.Text(f"Exported: {out_path}"), bgcolor="green")
        )

    def _compute_batch_bounding_box(self, boxes: list[RedactionBox]) -> PdfBox:
        if not boxes:
            raise ValueError("Cannot compute bounding box for empty box list")

        min_x = min(box.x for box in boxes)
        min_y = min(box.y for box in boxes)
        max_x = max(box.x + box.w for box in boxes)
        max_y = max(box.y + box.h for box in boxes)

        return PdfBox(x=min_x, y=min_y, w=max_x - min_x, h=max_y - min_y)

    def _group_boxes_by_batch(
        self, redactions: dict[str, dict[int, list[RedactionBox]]]
    ) -> dict[tuple[str, str], list[RedactionBox]]:
        batch_groups: dict[tuple[str, str], list[RedactionBox]] = {}

        for fname, pages in redactions.items():
            for page_idx, boxes in pages.items():
                for box in boxes:
                    batch_key = box.batch_id if box.batch_id else f"_unique_{box.id}"
                    group_key = (fname, batch_key)

                    if group_key not in batch_groups:
                        batch_groups[group_key] = []
                    batch_groups[group_key].append(box)

        return batch_groups

    def export_terms_to_excel(self, _: ft.ControlEvent) -> None:
        if not self.main_controller.terms_list:
            self.page.open(ft.SnackBar(ft.Text("No terms to export."), bgcolor="grey"))
            return

        def on_save_result(e: ft.FilePickerResultEvent) -> None:
            if not e.path:
                return
            path = e.path
            if not path.lower().endswith(".xlsx"):
                path += ".xlsx"
            raw_terms: list[dict[str, str | bool]] = [
                {"term": t.term, "active": t.active}
                for t in self.main_controller.terms_list
            ]
            success = export_terms_to_excel(raw_terms, path)
            if success:
                self.page.open(
                    ft.SnackBar(
                        ft.Text(
                            f"Exported {len(self.main_controller.terms_list)} terms to {os.path.basename(path)}"
                        ),
                        bgcolor="green",
                    )
                )
            else:
                self.page.open(
                    ft.SnackBar(ft.Text("Failed to export terms."), bgcolor="red")
                )

        picker = ft.FilePicker(on_result=on_save_result)
        self.page.overlay.append(picker)
        self.page.update()
        picker.save_file(
            dialog_title="Export Terms to Excel",
            file_name="search_terms.xlsx",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx"],
        )

    def import_terms_from_excel(self, _: ft.ControlEvent) -> None:
        def on_file_result(e: ft.FilePickerResultEvent) -> None:
            if not e.files or not e.files[0].path:
                return
            file_path = e.files[0].path
            imported_terms = import_terms_from_excel(file_path)
            if not imported_terms:
                self.page.open(
                    ft.SnackBar(
                        ft.Text("No terms found in file or error reading file."),
                        bgcolor="orange",
                    )
                )
                return

            def do_merge(_: ft.ControlEvent) -> None:
                existing_terms_lower = {
                    t.term.lower() for t in self.main_controller.terms_list
                }
                added = 0
                for term in imported_terms:
                    if term.lower() not in existing_terms_lower:
                        self.main_controller.terms_list.append(
                            TermItem(term=term, active=True)
                        )
                        existing_terms_lower.add(term.lower())
                        added += 1
                terms_dicts = [
                    {"term": t.term, "active": t.active}
                    for t in self.main_controller.terms_list
                ]
                self.page.client_storage.set("terms_list", terms_dicts)
                self.main_controller.search_term.refresh_term_table()
                import_dlg.open = False
                self.page.update()
                self.page.open(
                    ft.SnackBar(
                        ft.Text(f"Added {added} new terms (merged with existing)."),
                        bgcolor="green",
                    )
                )

            def do_replace(_: ft.ControlEvent) -> None:
                self.main_controller.terms_list.clear()
                for term in imported_terms:
                    self.main_controller.terms_list.append(
                        TermItem(term=term, active=True)
                    )
                terms_dicts = [
                    {"term": t.term, "active": t.active}
                    for t in self.main_controller.terms_list
                ]
                self.page.client_storage.set("terms_list", terms_dicts)
                self.main_controller.search_term.refresh_term_table()
                import_dlg.open = False
                self.page.update()
                self.page.open(
                    ft.SnackBar(
                        ft.Text(f"Replaced with {len(imported_terms)} terms."),
                        bgcolor="green",
                    )
                )

            def do_cancel(_: ft.ControlEvent) -> None:
                import_dlg.open = False
                self.page.update()

            import_dlg: ft.AlertDialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Import Terms"),
                content=ft.Text(
                    f"Found {len(imported_terms)} terms in file.\nMerge with existing terms or replace all?"
                ),
                actions=[
                    ft.TextButton("Merge", on_click=do_merge),
                    ft.TextButton("Replace All", on_click=do_replace),
                    ft.TextButton("Cancel", on_click=do_cancel),
                ],
            )
            self.page.overlay.append(import_dlg)
            import_dlg.open = True
            self.page.update()

        picker = ft.FilePicker(on_result=on_file_result)
        self.page.overlay.append(picker)
        self.page.update()
        picker.pick_files(
            dialog_title="Import Terms from Excel",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx", "xls"],
            allow_multiple=False,
        )

    def get_files_with_pending_redactions(self) -> list[str]:
        pending: set[str] = set()
        for fname, pages in self.main_controller.state.project.redactions.items():
            if any(boxes for boxes in pages.values()):
                pending.add(fname)
        for fname, entries in self.main_controller.state.project.toc_redactions.items():
            if entries:
                pending.add(fname)
        return sorted(pending)

    def _get_filtered_results_for_export(self) -> list[SearchResult]:
        all_results = self.main_controller.state.search.all_search_results
        filter_text = ""
        try:
            lv = refs["results_list"].current
            filter_text = str(getattr(lv, "data", "") or "")
        except Exception:
            filter_text = ""

        term_filter = str(
            self.main_controller.state.search.results_term_filter or ""
        ).strip()
        if term_filter.lower() == "all":
            term_filter = ""
        show_cci = bool(self.main_controller.state.search.show_cci_dosing_results)

        from src.core.state.app_state import ResultCategory

        filtered: list[SearchResult] = []
        for item in all_results:
            if self.main_controller.search_results.is_match_dismissed(item):
                continue
            if term_filter and item.term != term_filter:
                continue
            if not show_cci and item.category == ResultCategory.DOSAGE:
                continue
            hay = (item.term + item.match + item.context).lower()
            if filter_text and filter_text.lower() not in hay:
                continue
            filtered.append(item)
        return filtered

    def _build_file_path_map(self) -> dict[str, str]:
        path_map: dict[str, str] = {}
        for fpath in self.main_controller.state.project.file_list:
            if isinstance(fpath, str) and os.path.exists(fpath):
                path_map[os.path.basename(fpath)] = fpath
        for r in self.main_controller.state.search.all_search_results:
            fname = r.file_name
            fpath = r.file_path
            if fname and fpath and os.path.exists(fpath):
                path_map.setdefault(fname, fpath)
        return path_map
