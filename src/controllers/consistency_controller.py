"""
Controller for consistency scanning operations.

Finds unredacted occurrences of redacted text with background scanning and throttling.

NOTE: This controller remains unified (not split into scanning/resolution) because
gap detection and resolution share state, background coordination spans both concerns,
and resolution triggers re-scans, creating tight bidirectional coupling.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from datetime import datetime
from typing import Protocol

import flet as ft

import src.core.domain.consistency_checker as consistency_checker
from src.core.state.app_state import (
    RedactionBox,
    SearchResult,
)
from src.core.state.ui_state import refs
from src.ui.views import consistency_view

logger = logging.getLogger(__name__)


def convert_checker_gap_to_search_result(
    checker_gap: consistency_checker.ConsistencyGap,
) -> SearchResult:
    """Convert gap to SearchResult. Each occurrence is separate for accurate redaction."""
    from src.core.state.app_state import ResultCategory

    rects_list = []
    if checker_gap.rect:
        from src.core.state.app_state import PdfBox

        rects_list = [
            PdfBox(
                x=checker_gap.rect.x,
                y=checker_gap.rect.y,
                w=checker_gap.rect.w,
                h=checker_gap.rect.h,
            )
        ]

    return SearchResult(
        id=str(uuid.uuid4()),
        file_name=checker_gap.file_name,
        file_path=checker_gap.file_path,
        page=checker_gap.page,
        match=checker_gap.match_text,
        term="CCI:consistency",
        category=ResultCategory.GAP,
        context=checker_gap.context,
        batch_id="",
        redacted=False,
        dismissed=False,
        rects=rects_list,
    )


class MainControllerProtocol(Protocol):
    _consistency_scan_lock: threading.Lock
    _consistency_debounce_timer: threading.Timer | None
    _cancel_consistency_scan: bool
    state: AppStateProtocol
    redaction_data: RedactionDataProtocol
    viewer: ViewerProtocol


class AppStateProtocol(Protocol):
    consistency: ConsistencyStateProtocol
    ui: UIStateProtocol
    project: ProjectStateProtocol
    search: SearchStateProtocol
    viewer: ViewerStateProtocol


class ConsistencyStateProtocol(Protocol):
    consistency_running: bool
    consistency_scan_status: str
    consistency_last_scan: str


class UIStateProtocol(Protocol):
    current_tab: str


class ProjectStateProtocol(Protocol):
    file_list: list[str]
    redactions: dict[str, dict[int, list[RedactionBox]]]
    toc_redactions: dict[str, dict[int, str]]


class SearchStateProtocol(Protocol):
    search_running: bool
    all_search_results: list[SearchResult]


class RedactionDataProtocol(Protocol):
    def _add_redaction_raw(
        self, box: RedactionBox, page_idx: int, fname: str
    ) -> None: ...

    def _push_undo(self, action: object) -> None: ...

    def remove_batch_redaction(self, fname: str, batch_id: str) -> None: ...


class ViewerStateProtocol(Protocol):
    file_path: str | None
    page_index: int


class ViewerProtocol(Protocol):
    def render_viewer(self, initial: bool = False) -> None: ...

    def navigate_to_page(self, file_path: str, page_num: int) -> None: ...


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


class ConsistencyController:
    main_controller: MainControllerProtocol
    page: ft.Page

    def __init__(self, main_controller: MainControllerProtocol, page: ft.Page) -> None:
        self.main_controller = main_controller
        self.page = page

    def run_deep_consistency_scan(self, _: ft.ControlEvent | None = None) -> None:
        if not self.main_controller._consistency_scan_lock.acquire(blocking=False):
            self.page.open(
                ft.SnackBar(
                    ft.Text("Consistency scan already in progress"), bgcolor="orange"
                )
            )
            return

        self.main_controller._consistency_scan_lock.release()

        selected_files = (
            self.page.client_storage.get("selected_pdf_files")
            or self.main_controller.state.project.file_list
            or []
        )
        selected_files = [
            p
            for p in selected_files
            if isinstance(p, str) and os.path.exists(p) and p.lower().endswith(".pdf")
        ]
        if not selected_files:
            self.page.open(ft.SnackBar(ft.Text("No PDF files loaded."), bgcolor="grey"))
            return

        has_any = any(
            boxes
            for pages in self.main_controller.state.project.redactions.values()
            for boxes in pages.values()
            if boxes
        )
        if not has_any:
            self.page.open(
                ft.SnackBar(
                    ft.Text("No redactions to check. Apply some redactions first."),
                    bgcolor="grey",
                )
            )
            return

        self.main_controller.state.consistency.consistency_running = True
        self.main_controller.state.consistency.consistency_scan_status = "scanning"
        self._update_consistency_status_indicator()

        thread = threading.Thread(
            target=self._deep_consistency_worker,
            args=(selected_files,),
            daemon=True,
        )
        thread.start()

    def _deep_consistency_worker(self, selected_files: list[str]) -> None:
        try:
            gaps = consistency_checker.deep_consistency_scan(
                file_paths=selected_files,
                project_redactions=self.main_controller.state.project.redactions,
                min_text_length=2,
                progress_callback=None,
            )

            gap_results = [convert_checker_gap_to_search_result(g) for g in gaps]
            from src.core.state.app_state import ResultCategory

            self.main_controller.state.search.all_search_results = [
                r
                for r in self.main_controller.state.search.all_search_results
                if r.category != ResultCategory.GAP
            ]
            self.main_controller.state.search.all_search_results.extend(gap_results)

        except Exception as exc:
            logger.error(f"Deep consistency scan error: {exc}", exc_info=True)
            from src.core.state.app_state import ResultCategory

            self.main_controller.state.search.all_search_results = [
                r
                for r in self.main_controller.state.search.all_search_results
                if r.category != ResultCategory.GAP
            ]
        finally:
            self.main_controller.state.consistency.consistency_running = False
            self.main_controller.state.consistency.consistency_scan_status = "complete"

            try:
                from src.core.state.app_state import ResultCategory

                gap_count = sum(
                    1
                    for r in self.main_controller.state.search.all_search_results
                    if r.category == ResultCategory.GAP
                )
                logger.info(
                    f"Consistency scan complete: {gap_count} gaps, current_tab={self.main_controller.state.ui.current_tab}"
                )

                self._update_consistency_status_indicator()

                if (
                    gap_count > 0
                    or self.main_controller.state.ui.current_tab == "consistency"
                ):
                    logger.info(
                        f"Calling render_consistency_list with {gap_count} gaps"
                    )
                    consistency_view.render_consistency_list("")

                color = "green" if gap_count == 0 else "orange"
                msg = (
                    "No consistency gaps found!"
                    if gap_count == 0
                    else f"Found {gap_count} gap(s) — review in the Consistency tab."
                )
                self.page.open(ft.SnackBar(ft.Text(msg), bgcolor=color))
                self.page.update()

                if self.main_controller.viewer and hasattr(
                    self.main_controller, "state"
                ):
                    viewer_state = self.main_controller.state.viewer
                    if viewer_state.file_path:
                        self.main_controller.viewer.navigate_to_page(
                            viewer_state.file_path, viewer_state.page_index + 1
                        )
            except Exception as e:
                logger.error(f"Error in scan completion handler: {e}", exc_info=True)

            self._update_consistency_status_indicator()

    def _schedule_consistency_scan(self) -> None:
        """Schedule background scan after debounce period. Called when redactions change."""
        selected_files_raw = (
            self.page.client_storage.get("selected_pdf_files")
            or self.main_controller.state.project.file_list
            or []
        )
        selected_files: list[str] = (
            selected_files_raw if isinstance(selected_files_raw, list) else []
        )
        if not selected_files:
            return

        has_any_redactions = any(
            boxes
            for pages in self.main_controller.state.project.redactions.values()
            for boxes in pages.values()
            if boxes
        )
        if not has_any_redactions:
            from src.core.state.app_state import ResultCategory

            self.main_controller.state.search.all_search_results = [
                r
                for r in self.main_controller.state.search.all_search_results
                if r.category != ResultCategory.GAP
            ]
            self.main_controller.state.consistency.consistency_scan_status = "idle"
            self._update_consistency_status_indicator()
            return

        if self.main_controller.state.search.search_running:
            return

        if self.main_controller._consistency_debounce_timer is not None:
            self.main_controller._consistency_debounce_timer.cancel()

        self.main_controller._cancel_consistency_scan = True

        self.main_controller._consistency_debounce_timer = threading.Timer(
            5.0, self._run_background_consistency_scan
        )
        self.main_controller._consistency_debounce_timer.daemon = True
        self.main_controller._consistency_debounce_timer.start()

        self.main_controller.state.consistency.consistency_scan_status = "pending"
        self._update_consistency_status_indicator()

    def _run_background_consistency_scan(self) -> None:
        if not self.main_controller._consistency_scan_lock.acquire(blocking=False):
            return

        selected_files_raw = (
            self.page.client_storage.get("selected_pdf_files")
            or self.main_controller.state.project.file_list
            or []
        )
        selected_files_unfiltered: list[str] = (
            selected_files_raw if isinstance(selected_files_raw, list) else []
        )
        selected_files = [
            p
            for p in selected_files_unfiltered
            if isinstance(p, str) and os.path.exists(p) and p.lower().endswith(".pdf")
        ]
        if not selected_files:
            self.main_controller._consistency_scan_lock.release()
            return

        self.main_controller._cancel_consistency_scan = False
        self.main_controller.state.consistency.consistency_running = True
        self.main_controller.state.consistency.consistency_scan_status = "scanning"

        try:
            self._update_consistency_status_indicator()
        except Exception:
            pass

        def cancel_check() -> bool:
            return self.main_controller._cancel_consistency_scan

        # Counter for throttling UI updates (avoid overwhelming the UI thread)
        gap_update_counter = [0]
        last_ui_update = [time.time()]

        def on_gap_found(gap: consistency_checker.ConsistencyGap) -> None:
            if self.main_controller._cancel_consistency_scan:
                return

            self.main_controller.state.search.all_search_results.append(
                convert_checker_gap_to_search_result(gap)
            )
            gap_update_counter[0] += 1

            now = time.time()
            should_update = (
                gap_update_counter[0] % 10 == 0 or (now - last_ui_update[0]) > 1.0
            )

            if (
                should_update
                and self.main_controller.state.ui.current_tab == "consistency"
            ):
                last_ui_update[0] = now
                try:
                    consistency_view.render_consistency_list("")
                except Exception:
                    pass

        def worker() -> None:
            from src.core.state.app_state import ResultCategory

            self.main_controller.state.search.all_search_results = [
                r
                for r in self.main_controller.state.search.all_search_results
                if r.category != ResultCategory.GAP
            ]

            try:
                consistency_checker.deep_consistency_scan(
                    file_paths=selected_files,
                    project_redactions=self.main_controller.state.project.redactions,
                    min_text_length=2,
                    throttled=True,
                    cancel_flag=cancel_check,
                    gap_callback=on_gap_found,
                )

                if not self.main_controller._cancel_consistency_scan:
                    self.main_controller.state.consistency.consistency_last_scan = (
                        datetime.now().isoformat()
                    )
                    self.main_controller.state.consistency.consistency_scan_status = (
                        "complete"
                    )

            except Exception as exc:
                logger.error(f"Background consistency scan error: {exc}")
                if not self.main_controller._cancel_consistency_scan:
                    self.main_controller.state.consistency.consistency_scan_status = (
                        "idle"
                    )
            finally:
                self.main_controller.state.consistency.consistency_running = False
                self.main_controller._consistency_scan_lock.release()

                try:
                    self._update_consistency_status_indicator()
                    if self.main_controller.state.ui.current_tab == "consistency":
                        consistency_view.render_consistency_list("")

                    if self.main_controller.viewer and hasattr(
                        self.main_controller, "state"
                    ):
                        viewer_state = self.main_controller.state.viewer
                        if viewer_state.file_path:
                            self.main_controller.viewer.navigate_to_page(
                                viewer_state.file_path, viewer_state.page_index + 1
                            )
                except Exception:
                    pass

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _update_consistency_status_indicator(self) -> None:
        scan_btn = refs.get("btn_consistency_scan")
        if scan_btn and scan_btn.current:
            try:
                is_running = self.main_controller.state.consistency.consistency_running
                scan_btn.current.disabled = is_running
                if is_running:
                    scan_btn.current.icon = ft.Icons.HOURGLASS_EMPTY
                    scan_btn.current.text = "Scanning..."
                else:
                    scan_btn.current.icon = "refresh"
                    scan_btn.current.text = "Scan Now"
                scan_btn.current.update()
            except (AssertionError, Exception):
                pass

        indicator_ref = refs.get("consistency_status_indicator")
        if not indicator_ref or not indicator_ref.current:
            return

        status = self.main_controller.state.consistency.consistency_scan_status
        from src.core.state.app_state import ResultCategory

        gap_count = sum(
            1
            for r in self.main_controller.state.search.all_search_results
            if r.category == ResultCategory.GAP
        )

        if status == "scanning" or status == "pending":
            icon = ft.Icons.SYNC
            icon_color = "blue"
            text = "Scanning..." if status == "scanning" else "Pending..."
            text_color = "blue"
        elif gap_count > 0:
            icon = ft.Icons.WARNING
            icon_color = "orange"
            text = f"{gap_count} gap{'s' if gap_count != 1 else ''}"
            text_color = "orange"
        elif status == "complete":
            icon = ft.Icons.CHECK_CIRCLE
            icon_color = "green"
            text = "No gaps"
            text_color = "green"
        else:
            icon = ft.Icons.REMOVE_CIRCLE_OUTLINE
            icon_color = "grey"
            text = "Idle"
            text_color = "grey"

        indicator_ref.current.content = ft.Row(
            [
                ft.Icon(icon, size=14, color=icon_color),
                ft.Text(text, size=10, color=text_color),
            ],
            spacing=4,
        )
        indicator_ref.current.update()
        _safe_update(indicator_ref.current)
