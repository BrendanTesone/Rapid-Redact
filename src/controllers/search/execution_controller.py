"""
execution_controller.py - Controller for search execution and threading
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import TYPE_CHECKING, Protocol, TypedDict

import flet as ft

from src.config import AppConfig
from src.ui.views import matches_view, bookmarks_view
from src.core.state.ui_state import refs
from src.core.state.app_state import (
    AppState,
    SearchResult,
    TermItem,
    DismissKey,
    PdfBox,
)

if TYPE_CHECKING:
    from src.controllers.viewer_controller import ViewerController
    from src.controllers.redaction.rendering_controller import (
        RedactionRenderingController,
    )

logger = logging.getLogger(__name__)


class SearchResultDict(TypedDict, total=False):
    file_name: str
    file_path: str
    page: int
    match: str
    term: str
    x0: float
    y0: float
    x1: float
    y1: float
    context: str
    batch_id: str
    redacted: bool
    dismissed: bool


class BookmarkResultDict(TypedDict, total=False):
    file_name: str
    file_path: str
    page: int
    end_page: int
    level: int
    title: str
    term: str
    original_index: int


class MainControllerProtocol(Protocol):
    state: AppState
    terms_list: list[TermItem]
    config: AppConfig
    if TYPE_CHECKING:
        viewer: ViewerController
        redaction_rendering: RedactionRenderingController


class ResultsControllerProtocol(Protocol):
    def refresh_results_term_filter_options(self) -> None: ...

    @staticmethod
    def _dismiss_key(item: SearchResult) -> DismissKey: ...


class ExecutionController:
    _search_lock = threading.Lock()

    def __init__(
        self,
        main_controller: MainControllerProtocol,
        page: ft.Page,
        results_controller: ResultsControllerProtocol | None = None,
    ) -> None:
        self.main_controller: MainControllerProtocol = main_controller
        self.page: ft.Page = page
        self._results_controller: ResultsControllerProtocol | None = results_controller

    @property
    def state(self) -> AppState:
        return self.main_controller.state

    @property
    def terms_list(self) -> list[TermItem]:
        return self.main_controller.terms_list

    @property
    def results_controller(self) -> ResultsControllerProtocol:
        if self._results_controller is None:
            raise RuntimeError(
                "ResultsController not set - must be injected after initialization"
            )
        return self._results_controller

    def set_results_controller(
        self, results_controller: ResultsControllerProtocol
    ) -> None:
        self._results_controller = results_controller

    def run_search(self, _: ft.ControlEvent) -> None:
        with self._search_lock:
            if self.state.search.search_running:
                self.page.open(
                    ft.SnackBar(
                        ft.Text("Search already in progress..."), bgcolor="orange"
                    )
                )
                return
            self.state.search.search_running = True

        folder_val = self.page.client_storage.get("pdf_folder")
        folder = str(folder_val) if folder_val else ""
        if not folder:
            self.page.open(ft.SnackBar(ft.Text("No folder selected."), bgcolor="grey"))
            return

        active_terms = [t.term for t in self.terms_list if t.active]
        self.state.search.active_search_terms = active_terms

        search_progress_ref = refs.get("search_progress")
        if search_progress_ref and search_progress_ref.current:
            search_progress_ref.current.visible = True
            search_progress_ref.current.value = 0
        search_status_ref = refs.get("search_status")
        if search_status_ref and search_status_ref.current:
            search_status_ref.current.value = "Starting search..."

        matches_progress_ref = refs.get("matches_progress")
        if matches_progress_ref and matches_progress_ref.current:
            matches_progress_ref.current.visible = True
            matches_progress_ref.current.value = 0
        self.page.update()

        self.state.search.all_search_results.clear()

        context_size = self.main_controller.config.search.min_context
        selected_files_val = (
            self.page.client_storage.get("selected_pdf_files")
            or self.state.project.file_list
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
            target=self._search_worker,
            args=(
                folder,
                active_terms,
                context_size,
                selected_files,
            ),
            daemon=True,
        )
        thread.start()

    def _search_worker(
        self,
        folder: str,
        active_terms: list[str],
        context_size: int,
        selected_files: list[str],
    ) -> None:
        search_start = time.monotonic()

        try:
            search_status_ref = refs.get("search_status")
            if search_status_ref and search_status_ref.current:
                search_status_ref.current.value = "Searching bookmarks..."
                try:
                    self.page.update()
                except Exception:
                    pass

            def _progress(completed: int, total: int, fname: str) -> None:
                try:
                    if refs["search_progress"].current:
                        refs["search_progress"].current.value = (
                            completed / total if total else 0
                        )
                    if refs["search_status"].current:
                        refs["search_status"].current.value = (
                            f"Searched {completed}/{total} files — {fname}"
                        )
                    self.page.update()
                except Exception:
                    pass

            raw_results_dicts: list[
                dict[str, str | int | float | bool | list[PdfBox]]
            ] = []

            from src.core.domain.pdf_search_split import search_pdfs_for_terms

            iterator = search_pdfs_for_terms(
                folder,
                active_terms,
                context_size,
                selected_files=selected_files,
            )

            for item in iterator:
                if "progress" in item:
                    search_progress_ref = refs.get("search_progress")
                    if search_progress_ref and search_progress_ref.current:
                        progress_val = item.get("progress", 0.0)
                        if isinstance(progress_val, (int, float)):
                            search_progress_ref.current.value = float(progress_val)
                    search_status_ref = refs.get("search_status")
                    if search_status_ref and search_status_ref.current:
                        search_status_ref.current.value = (
                            f"Scanning: {item.get('current_file', '')}"
                        )
                    matches_progress_ref = refs.get("matches_progress")
                    if matches_progress_ref and matches_progress_ref.current:
                        progress_val = item.get("progress", 0.0)
                        if isinstance(progress_val, (int, float)):
                            matches_progress_ref.current.value = float(progress_val)
                    try:
                        self.page.update()
                    except Exception:
                        pass
                    continue
                if item.get("type") == "match":
                    item.setdefault("redacted", False)
                    item.setdefault("dismissed", False)
                    raw_results_dicts.append(item)

            for r in raw_results_dicts:
                r.setdefault("redacted", False)
                r.setdefault("dismissed", False)

            search_results: list[SearchResult] = []
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

                    from src.core.state.app_state import ResultCategory

                    term = str(result_dict.get("term", ""))
                    category_str = result_dict.get("category", "matches")
                    category = ResultCategory(category_str)

                    search_results.append(
                        SearchResult(
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
                    )
                except (ValueError, TypeError, KeyError):
                    continue

            self.state.search.all_search_results = search_results

            dismissed_set = self.state.search.dismissed_matches
            for result in self.state.search.all_search_results:
                key = self.results_controller._dismiss_key(result)
                if key in dismissed_set:
                    result.dismissed = True

            # Match search results to existing redactions by term, match text, and batch_id
            for result in self.state.search.all_search_results:
                file_redactions = self.state.project.redactions.get(
                    result.file_name, {}
                )
                page_redactions = file_redactions.get(result.page - 1, [])

                for box in page_redactions:
                    if (
                        box.batch_id
                        and box.term == result.term
                        and box.match
                        and result.match
                        and box.match.lower().strip() == result.match.lower().strip()
                    ):
                        result.redacted = True
                        result.batch_id = box.batch_id
                        break

        except Exception as ex:
            logger.error(f"Search worker error: {ex}")
        finally:
            with self._search_lock:
                self.state.search.search_running = False
            elapsed = time.monotonic() - search_start
            try:
                self.results_controller.refresh_results_term_filter_options()
                if self.state.ui.current_tab == "bookmarks":
                    bookmarks_view.render_bookmarks_list("")
                else:
                    matches_view.render_text_results_list("")

                if self.state.viewer.file_path:
                    self.main_controller.viewer.navigate_to_page(
                        self.state.viewer.file_path, self.state.viewer.page_index + 1
                    )

                search_progress_ref = refs.get("search_progress")
                if search_progress_ref and search_progress_ref.current:
                    search_progress_ref.current.visible = False

                matches_progress_ref = refs.get("matches_progress")
                if matches_progress_ref and matches_progress_ref.current:
                    matches_progress_ref.current.visible = False

                search_status_ref = refs.get("search_status")
                if search_status_ref and search_status_ref.current:
                    unique_count = len(self.state.search.all_search_results)
                    dismissed_count = sum(
                        1 for r in self.state.search.all_search_results if r.dismissed
                    )
                    dismiss_note = (
                        f", {dismissed_count} dismissed" if dismissed_count > 0 else ""
                    )
                    search_status_ref.current.value = (
                        f"Found {unique_count} matches{dismiss_note} in {elapsed:.1f}s."
                    )

                self.page.update()
            except Exception:
                pass
