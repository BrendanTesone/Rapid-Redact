from __future__ import annotations

from typing import Protocol, TYPE_CHECKING

import flet as ft

from src.ui.views import matches_view
from src.core.state.ui_state import refs
from src.core.state.app_state import (
    AppState,
    SearchResult,
    DismissKey,
    ResultCategory,
    TermItem,
)

if TYPE_CHECKING:
    from src.config import AppConfig


class MainControllerProtocol(Protocol):
    state: AppState
    config: AppConfig
    terms_list: list[TermItem]

    @property
    def viewer(self) -> ViewerControllerProtocol: ...

    @property
    def redaction_data(self) -> RedactionDataControllerProtocol: ...

    @property
    def redaction_rendering(self) -> RedactionRenderingControllerProtocol: ...


class ViewerControllerProtocol(Protocol):
    def navigate_to_page(self, file_path: str, page_num: int) -> None: ...

    def _create_placeholder(self, page_idx: int) -> ft.Container: ...

    def _render_page_strip(self) -> None: ...


class RedactionDataControllerProtocol(Protocol):
    def remove_batch_redaction(self, file_name: str, batch_id: str) -> None: ...


class RedactionRenderingControllerProtocol(Protocol):
    def refresh_page_overlays(self, page_index: int) -> None: ...


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


class ResultsController:
    def __init__(
        self,
        main_controller: MainControllerProtocol,
        page: ft.Page,
        viewer_controller: ViewerControllerProtocol | None = None,
        redaction_data_controller: RedactionDataControllerProtocol | None = None,
    ) -> None:
        self.main_controller: MainControllerProtocol = main_controller
        self.page: ft.Page = page
        self._viewer_controller: ViewerControllerProtocol | None = viewer_controller
        self._redaction_data_controller: RedactionDataControllerProtocol | None = (
            redaction_data_controller
        )

    @property
    def state(self) -> AppState:
        return self.main_controller.state

    @property
    def viewer(self) -> ViewerControllerProtocol:
        if self._viewer_controller is None:
            self._viewer_controller = self.main_controller.viewer
        return self._viewer_controller

    @property
    def redaction_data(self) -> RedactionDataControllerProtocol:
        if self._redaction_data_controller is None:
            self._redaction_data_controller = self.main_controller.redaction_data
        return self._redaction_data_controller

    @staticmethod
    def _dismiss_key(item: SearchResult) -> DismissKey:
        return DismissKey(
            file_name=item.file_name,
            page=item.page,
            match_text=item.match.lower().strip(),
            term=item.term,
        )

    def is_match_dismissed(self, item: SearchResult) -> bool:
        key = self._dismiss_key(item)
        return key in self.state.search.dismissed_matches

    def dismiss_match(self, item: SearchResult) -> None:
        self.state.search.dismissed_matches.add(self._dismiss_key(item))

        for result in self.state.search.all_search_results:
            if result.id == item.id:
                result.dismissed = True
                if result.redacted:
                    if result.batch_id:
                        self.redaction_data.remove_batch_redaction(
                            result.file_name, result.batch_id
                        )
                    result.redacted = False
                    result.batch_id = ""
                break

        self._refresh_results_list_by_category(item.category)

        if self.state.viewer.file_path:
            self.main_controller.viewer.navigate_to_page(
                self.state.viewer.file_path, self.state.viewer.page_index + 1
            )

    def restore_match(self, item: SearchResult) -> None:
        key = self._dismiss_key(item)
        dismissed = self.state.search.dismissed_matches
        dismissed.discard(key)

        for result in self.state.search.all_search_results:
            if result.id == item.id:
                result.dismissed = False
                break

        self._refresh_results_list_by_category(item.category)

        if self.state.viewer.file_path:
            self.main_controller.viewer.navigate_to_page(
                self.state.viewer.file_path, self.state.viewer.page_index + 1
            )

    def on_toggle_show_dismissed(self, e: ft.ControlEvent) -> None:
        self.state.search.show_dismissed = bool(getattr(e.control, "value", False))

        if self.state.ui.current_tab == "dose":
            from src.ui.views import dose_view

            dose_view.render_dose_results_list()
        else:
            current_filter = ""
            try:
                current_filter = str(refs["results_list"].current.data or "")
            except Exception:
                pass
            matches_view.render_text_results_list(current_filter)

    def _refresh_results_list_by_category(self, category: ResultCategory) -> None:
        from src.core.state.app_state import ResultCategory

        if category == ResultCategory.DOSAGE:
            from src.ui.views import dose_view

            dose_view.render_dose_results_list()
        elif category == ResultCategory.MATCHES:
            results_list_ref = refs.get("results_list")
            current_filter = (
                str(results_list_ref.current.data or "")
                if results_list_ref and results_list_ref.current
                else ""
            )
            matches_view.render_text_results_list(current_filter)
        elif category == ResultCategory.GAP:
            from src.ui.views import consistency_view

            consistency_view.render_consistency_list()
        elif category == ResultCategory.AI:
            from src.ui.views import ai_detection_view

            ai_detection_view.render_ai_detections_list()

    def refresh_results_term_filter_options(self) -> None:
        """Only shows terms that are both found in search results AND defined in the project's term list."""
        dd_ref = refs.get("dd_results_term_filter")
        dd = dd_ref.current if dd_ref else None
        if not dd:
            return

        project_term_strings = {t.term for t in self.main_controller.terms_list}

        terms = sorted(
            {
                r.term
                for r in self.state.search.all_search_results
                if r.term and r.term != "CCI:dosing" and r.term in project_term_strings
            }
        )
        dd.options = [ft.dropdown.Option("All")] + [
            ft.dropdown.Option(t) for t in terms
        ]
        current = str(self.state.search.results_term_filter or "").strip()
        if current.lower() == "all":
            current = ""
        if current and current not in terms:
            current = ""
        dd.value = "All" if not current else current
        self.state.search.results_term_filter = current
        _safe_update(dd)

    def on_results_term_filter_change(self, e: ft.ControlEvent) -> None:
        raw = str(getattr(e.control, "value", "") or "").strip()
        val = "" if raw.lower() == "all" else raw
        self.state.search.results_term_filter = val
        self.state.search.current_term = val
        try:
            self.page.client_storage.set("results_term_filter", val)
        except Exception:
            pass
        current_filter_text = ""
        try:
            results_list_ref = refs.get("results_list")
            if results_list_ref and results_list_ref.current:
                current_filter_text = str(results_list_ref.current.data or "")
        except Exception:
            pass
        matches_view.render_text_results_list(current_filter_text)

        if self.state.viewer.file_path:
            self.main_controller.viewer.navigate_to_page(
                self.state.viewer.file_path, self.state.viewer.page_index + 1
            )
