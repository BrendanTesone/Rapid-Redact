from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import TYPE_CHECKING

import flet as ft

from src.core.state.ui_state import refs
from src.core.state.app_state import PdfBox

if TYPE_CHECKING:
    from src.controllers.main_controller import MainController
    from src.core.state.app_state import SearchResult

logger = logging.getLogger(__name__)


class DoseController:
    """Handles dose detection and management."""

    _search_lock = threading.Lock()

    def __init__(self, main_controller: MainController, page: ft.Page) -> None:
        self.main_controller = main_controller
        self.page = page

    def run_dose_scan(self) -> None:
        with self._search_lock:
            if self.main_controller.state.search.search_running:
                self.page.open(
                    ft.SnackBar(
                        ft.Text("Search already in progress..."), bgcolor="orange"
                    )
                )
                return
            self.main_controller.state.search.search_running = True

        folder_val = self.page.client_storage.get("pdf_folder")
        folder = str(folder_val) if folder_val else ""
        if not folder:
            self.page.open(ft.SnackBar(ft.Text("No folder selected."), bgcolor="grey"))
            return

        dose_progress_ref = refs.get("dose_progress")
        if dose_progress_ref and dose_progress_ref.current:
            dose_progress_ref.current.visible = True
            dose_progress_ref.current.value = 0
        self.page.update()

        selected_files_val = (
            self.page.client_storage.get("selected_pdf_files")
            or self.main_controller.state.project.file_list
            or []
        )
        selected_files: list[str] = []
        if isinstance(selected_files_val, list):
            for p in selected_files_val:
                if (
                    isinstance(p, str)
                    and os.path.exists(p)
                    and p.lower().endswith(".pdf")
                ):
                    selected_files.append(p)

        thread = threading.Thread(
            target=self._dose_scan_worker,
            args=(
                folder,
                selected_files,
            ),
            daemon=True,
        )
        thread.start()

    def _dose_scan_worker(
        self,
        folder: str,
        selected_files: list[str],
    ) -> None:
        search_start = time.monotonic()

        try:
            from src.core.domain.pdf_search_split import search_pdfs_for_doses
            from src.core.state.app_state import ResultCategory, SearchResult

            # Clear existing dose results to prevent duplicates
            self.main_controller.state.search.all_search_results = [
                r
                for r in self.main_controller.state.search.all_search_results
                if r.category != ResultCategory.DOSAGE
            ]

            raw_results_dicts: list[
                dict[str, str | int | float | bool | list[PdfBox]]
            ] = []

            iterator = search_pdfs_for_doses(
                folder,
                dosing_context_window_words=self.main_controller.config.search.dosing_context_window_words,
                selected_files=selected_files,
            )

            for item in iterator:
                if "progress" in item:
                    dose_progress_ref = refs.get("dose_progress")
                    if dose_progress_ref and dose_progress_ref.current:
                        progress_val = item.get("progress", 0.0)
                        if isinstance(progress_val, (int, float)):
                            dose_progress_ref.current.value = float(progress_val)
                    try:
                        self.page.update()
                    except Exception:
                        pass
                    continue
                if item.get("type") == "match":
                    item.setdefault("redacted", False)
                    item.setdefault("dismissed", False)
                    raw_results_dicts.append(item)

            for result_dict in raw_results_dicts:
                try:
                    page_val: str | int | float | bool | list[PdfBox] = result_dict.get(
                        "page", 0
                    )
                    rects_val: str | int | float | bool | list[PdfBox] = (
                        result_dict.get("rects", [])
                    )

                    rects_list: list[PdfBox] = []
                    if isinstance(rects_val, list):
                        for rect_item in rects_val:
                            try:
                                if isinstance(rect_item, PdfBox):
                                    rects_list.append(rect_item)
                                elif isinstance(rect_item, dict):  # type: ignore[unreachable]
                                    rects_list.append(
                                        PdfBox(
                                            x=float(rect_item.get("x", 0)),
                                            y=float(rect_item.get("y", 0)),
                                            w=float(rect_item.get("w", 0)),
                                            h=float(rect_item.get("h", 0)),
                                        )
                                    )
                            except (
                                ValueError,
                                TypeError,
                                KeyError,
                                AttributeError,
                            ) as e:
                                logger.warning(
                                    f"Failed to convert rect for {result_dict.get('file_name')} "
                                    f"page {result_dict.get('page')}: {e}"
                                )

                    term = str(result_dict.get("term", ""))
                    category_str = result_dict.get("category", "dosage")
                    category = ResultCategory(category_str)

                    dose_result = SearchResult(
                        id=str(uuid.uuid4()),
                        file_name=str(result_dict.get("file_name", "")),
                        file_path=str(result_dict.get("file_path", "")),
                        page=(
                            int(page_val)
                            if isinstance(page_val, (int, float, str))
                            else 0
                        ),
                        match=str(result_dict.get("match", "")),
                        term=term,
                        category=category,
                        context=str(result_dict.get("context", "")),
                        batch_id=str(result_dict.get("batch_id", "")),
                        redacted=bool(result_dict.get("redacted", False)),
                        dismissed=bool(result_dict.get("dismissed", False)),
                        rects=rects_list,
                    )
                    self.main_controller.state.search.all_search_results.append(
                        dose_result
                    )
                except (ValueError, TypeError, KeyError):
                    continue

            dismissed_set = self.main_controller.state.search.dismissed_matches
            for result in self.main_controller.state.search.all_search_results:
                if result.category == ResultCategory.DOSAGE:
                    key = self.main_controller.search_results._dismiss_key(result)
                    if key in dismissed_set:
                        result.dismissed = True

            # Mark results as redacted if matching redaction exists (by term, match text, and batch_id)
            for result in self.main_controller.state.search.all_search_results:
                if result.category == ResultCategory.DOSAGE:
                    file_redactions = self.main_controller.state.project.redactions.get(
                        result.file_name, {}
                    )
                    page_redactions = file_redactions.get(result.page - 1, [])

                    for box in page_redactions:
                        if (
                            box.batch_id
                            and box.term == result.term
                            and box.match
                            and result.match
                            and box.match.lower().strip()
                            == result.match.lower().strip()
                        ):
                            result.redacted = True
                            result.batch_id = box.batch_id
                            break

        except Exception as ex:
            logger.error(f"Dose scan worker error: {ex}")
        finally:
            with self._search_lock:
                self.main_controller.state.search.search_running = False
            elapsed = time.monotonic() - search_start
            try:
                if self.main_controller.state.ui.current_tab == "dose":
                    from src.ui.views import dose_view

                    dose_view.render_dose_results_list()

                dose_progress_ref = refs.get("dose_progress")
                if dose_progress_ref and dose_progress_ref.current:
                    dose_progress_ref.current.visible = False

                dose_count = len(
                    [
                        r
                        for r in self.main_controller.state.search.all_search_results
                        if r.category == ResultCategory.DOSAGE and not r.dismissed
                    ]
                )

                color = "green" if dose_count == 0 else "orange"
                msg = (
                    "No doses found!"
                    if dose_count == 0
                    else f"Found {dose_count} dose(s) in {elapsed:.1f}s."
                )
                self.page.open(ft.SnackBar(ft.Text(msg), bgcolor=color))

                self.page.update()

                viewer_state = self.main_controller.state.viewer
                if viewer_state.file_path:
                    self.main_controller.viewer.navigate_to_page(
                        viewer_state.file_path, viewer_state.page_index + 1
                    )
            except Exception:
                pass

    def dismiss_dose(self, result: SearchResult) -> None:
        self.main_controller.search_results.dismiss_match(result)

    def restore_dose(self, result: SearchResult) -> None:
        self.main_controller.search_results.restore_match(result)
