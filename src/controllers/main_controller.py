"""
Main orchestration hub - owns AppState and instantiates all sub-controllers.

All domain logic is delegated to specialized sub-controllers.
Callers should access controllers directly (e.g., controller.bookmark.load_file_result()).
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass

import flet as ft

from src.core.domain.pdf_rendering import list_pdf_files
import src.ui.layout as ui_layout
from src.config import AppConfig
from src.core.state.app_state import AppState, TermItem
from src.core.state.ui_state import refs
from src.ui.views import (
    viewer_view,
    consistency_view,
    bookmarks_view,
    files_view,
    matches_view,
)
from src.ui import dialogs

from src.controllers.viewer_controller import ViewerController
from src.controllers.search.term_controller import TermController
from src.controllers.search.results_controller import ResultsController
from src.controllers.search.execution_controller import ExecutionController
from src.controllers.bookmark_controller import BookmarkController
from src.controllers.redaction.data_controller import RedactionDataController
from src.controllers.redaction.rendering_controller import RedactionRenderingController
from src.controllers.redaction.interaction_controller import (
    RedactionInteractionController,
)
from src.controllers.persistence.project_controller import ProjectPersistenceController
from src.controllers.persistence.export_controller import ExportController
from src.controllers.ai.ai_detection_controller import AIDetectionController
from src.controllers.ai.llm_client import LiteLLMClient
from src.controllers.consistency_controller import ConsistencyController
from src.ui.rendering.gesture_handler import UIGesturesController

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _safe_update(control: ft.Control | None) -> bool:
    """Call update() on control if attached to page."""
    if control and getattr(control, "page", None) is not None:
        control.update()
        return True
    return False


@dataclass(slots=True)
class _DragData:
    box: ft.Container | None = None
    start_x: float = 0.0
    start_y: float = 0.0
    page_index: int = 0
    edit_preview: ft.Container | None = None
    edit_box_id: str | None = None
    edit_kind: str | None = None
    edit_page_index: int = 0
    edit_scale: float = 1.0
    ex0: float = 0.0
    ey0: float = 0.0
    ew0: float = 0.0
    eh0: float = 0.0
    acc_dx: float = 0.0
    acc_dy: float = 0.0


class MainController:
    """Main orchestration hub - owns AppState and all sub-controllers."""

    _search_lock: threading.Lock = threading.Lock()
    _consistency_scan_lock: threading.Lock = threading.Lock()
    _page_update_lock: threading.Lock = threading.Lock()

    page: ft.Page
    state: AppState
    config: AppConfig

    terms_list: list[TermItem]
    drag_data: _DragData
    _hover_box_id: str | None
    _handle_controls: dict[str, list[ft.Container]]
    _folder_picker: ft.FilePicker | None
    _last_resize_update: float

    viewer: ViewerController
    search_term: TermController
    search_results: ResultsController
    search_execution: ExecutionController
    bookmark: BookmarkController
    redaction_data: RedactionDataController
    redaction_rendering: RedactionRenderingController
    redaction_interaction: RedactionInteractionController
    project_persistence: ProjectPersistenceController
    export: ExportController
    consistency: ConsistencyController
    ui_gestures: UIGesturesController

    def __init__(self, page: ft.Page, config: AppConfig) -> None:
        self.page = page
        self.state = AppState()
        self.config = config

        raw_terms = page.client_storage.get("terms_list") or []
        self.terms_list = []
        for item in raw_terms:
            if isinstance(item, dict):
                term = item.get("term", "")
                # Support both 'active' (new) and 'enabled' (legacy) storage keys
                active = item.get("active", item.get("enabled", False))
                if isinstance(term, str) and isinstance(active, bool):
                    self.terms_list.append(TermItem(term=term, active=active))
        self.drag_data = _DragData()
        self._hover_box_id = None
        self._handle_controls = {}
        self._folder_picker = None
        self._consistency_debounce_timer: threading.Timer | None = None
        self._cancel_consistency_scan: bool = False
        self._last_resize_update = 0.0

        self.viewer = ViewerController(self, page)
        self.redaction_data = RedactionDataController(self, page)
        self.search_term = TermController(self, page)
        self.search_results = ResultsController(
            self, page, self.viewer, self.redaction_data
        )
        self.search_execution = ExecutionController(self, page, self.search_results)
        self.search_execution.set_results_controller(self.search_results)
        self.bookmark = BookmarkController(self, page)
        self.redaction_rendering = RedactionRenderingController(
            self, page, self.redaction_data  # type: ignore[arg-type]
        )
        self.redaction_interaction = RedactionInteractionController(
            self, page, self.redaction_data, self.redaction_rendering
        )
        self.project_persistence = ProjectPersistenceController(self, page)
        self.export = ExportController(self, page)
        self.consistency = ConsistencyController(self, page)  # type: ignore[arg-type]

        from src.controllers.dose_controller import DoseController
        self.dose = DoseController(self, page)

        llm_client = LiteLLMClient(self.config.ai_api)
        self.ai_detection = AIDetectionController(
            self.state, self.state.ai_detection, llm_client, self
        )

        from src.controllers.amendment.amendment_controller import AmendmentController
        self.amendment = AmendmentController(self)

        self.ui_gestures = UIGesturesController(self, page)

    def create_view(self) -> ft.Control:
        from src.ui.views import base_results_view

        base_results_view.register_controller(self)
        viewer_view.set_controller(self)
        files_view.register_controller(self)
        bookmarks_view.register_controller(self)

        self.page.overlay.append(self.project_persistence._project_save_picker)
        self.page.overlay.append(self.project_persistence._project_load_picker)
        self.page.overlay.append(self.amendment._redline_picker)
        self.page.overlay.append(self.amendment._destination_picker)

        root = ui_layout.build_layout(controller=self)

        selected_files = self.page.client_storage.get("selected_pdf_files") or []
        folder = self.page.client_storage.get("pdf_folder")

        if selected_files:
            valid = [
                p for p in selected_files if isinstance(p, str) and os.path.exists(p)
            ]
            self.state.project.file_list = valid
            if refs["folder_text"].current:
                base_folder = os.path.dirname(valid[0]) if valid else (folder or "")
                refs["folder_text"].current.value = (
                    f"{base_folder}  ({len(valid)} PDF(s) selected)"
                )
            files_view.render_file_list()
        elif folder:
            if refs["folder_text"].current:
                refs["folder_text"].current.value = folder
            self.state.project.file_list = list_pdf_files(folder)
            files_view.render_file_list()

        self._apply_tab_ui_state(tab_name=self.state.ui.current_tab)
        _dm = self.state.redaction.drawing_mode
        _sm = self.state.redaction.selection_mode
        _startup_mode = (
            "rect_repeat"
            if _dm == "repeat"
            else ("highlight_redact" if _sm == "select_redact" else "rect_single")
        )
        self.ui_gestures.set_mode(_startup_mode)

        if self.state.ui.current_tab == "viewer":
            viewer_view.render_viewer_list("")

        persisted_smart = self.page.client_storage.get("smart_dosing_filter_enabled")
        if persisted_smart is not None:
            self.state.search.smart_dosing_filter_enabled = bool(persisted_smart)

        self.viewer._restore_ui_preferences()

        return root

    def on_keyboard(self, e: ft.KeyboardEvent) -> None:
        key = e.key

        if e.ctrl:
            if key == "Z":
                self.redaction_data.undo()
                return
            if key == "Y":
                self.redaction_data.redo()
                return
            if key == "A":
                self.redaction_interaction.select_all_annotations_on_page()
                return
            return

        if key == "Delete":
            self.redaction_interaction.delete_selected_annotations()
            return

        file_path = self.state.viewer.file_path
        if not file_path:
            return
        if key in ("Arrow Left", "Page Up"):
            self.viewer.change_page(-1)
            return
        if key in ("Arrow Right", "Page Down"):
            self.viewer.change_page(1)
            return
        if key == "Home":
            if int(self.state.viewer.page_index) != 0:
                self.viewer.navigate_to_page(file_path, 1)
            return
        if key == "End":
            total = int(self.state.viewer.total_pages)
            if total > 0 and int(self.state.viewer.page_index) != total - 1:
                self.viewer.navigate_to_page(file_path, total)
            return

    def _show_shortcuts_dialog(self) -> None:
        dialog = dialogs.create_shortcuts_dialog(self.page)
        self.page.open(dialog)

    def switch_tab(
        self, e: ft.ControlEvent | None, tab_name: str | None = None
    ) -> None:
        if e and hasattr(e.control, "value"):
            new_tab = e.control.value
        elif tab_name:
            new_tab = tab_name
        else:
            return

        self.state.ui.current_tab = new_tab

        # Track last visited results tab for page strip filtering
        if new_tab in (
            "matches",
            "dose",
            "consistency",
            "ai_detect",
            "amendment_transfer",
            "pd_checker",
        ):
            self.state.ui.last_results_tab = new_tab

        self._apply_tab_ui_state(new_tab)
        self.page.client_storage.set("current_tab", new_tab)

        if new_tab == "viewer":
            viewer_view.render_viewer_list("")
        elif new_tab == "matches":
            matches_view.render_text_results_list()
            self.page.update()
            self.search_results.refresh_results_term_filter_options()
        elif new_tab == "bookmarks":
            bookmarks_view.render_bookmarks_list()
        elif new_tab == "dose":
            from src.ui.views import dose_view
            dose_view.render_dose_results_list()
        elif new_tab == "consistency":
            consistency_view.render_consistency_list("")
        elif new_tab == "ai_detect":
            from src.ui.views import ai_detection_view
            ai_detection_view.render_ai_detections_list()
        elif new_tab == "pd_checker":
            from src.ui.views import pd_checker_view
            pd_checker_view.refresh_pd_checker_results()

        # Navigate to current page to refresh overlays (reads current_tab for filtering)
        if self.state.viewer.file_path:
            self.viewer.navigate_to_page(
                self.state.viewer.file_path, self.state.viewer.page_index + 1
            )

    def _apply_tab_ui_state(self, tab_name: str) -> None:
        dropdown = refs.get("tab_dropdown")
        if dropdown and dropdown.current:
            dropdown.current.value = tab_name
            _safe_update(dropdown.current)

        tab_area = refs.get("tab_content_area")
        if tab_area and tab_area.current:
            if tab_name == "viewer":
                tab_area.current.content = ui_layout.build_view_viewer(self)
            elif tab_name == "files":
                tab_area.current.content = ui_layout.build_view_files(self)
            elif tab_name == "matches":
                tab_area.current.content = ui_layout.build_view_text_matches(self)
            elif tab_name == "bookmarks":
                tab_area.current.content = ui_layout.build_view_bookmarks(self)
            elif tab_name == "dose":
                tab_area.current.content = ui_layout.build_view_dose(self)
            elif tab_name == "consistency":
                tab_area.current.content = ui_layout.build_view_consistency(self)
            elif tab_name == "ai_detect":
                tab_area.current.content = ui_layout.build_view_ai_detect(self)
            elif tab_name == "amendment_transfer":
                tab_area.current.content = ui_layout.build_view_amendment_transfer(self)
            elif tab_name == "pd_checker":
                tab_area.current.content = ui_layout.build_view_pd_checker(self)

        self.page.update()

    def on_panel_resize(self, e: ft.DragUpdateEvent, panel: str) -> None:
        import time

        now = time.time() * 1000
        if now - self._last_resize_update < self.config.ui.resize_throttle_ms:
            return
        self._last_resize_update = now

        if panel == "left":
            left_col = refs.get("left_col")
            if left_col and left_col.current:
                new_width = max(
                    self.config.ui.panel_left_min_width,
                    min(
                        self.config.ui.panel_left_max_width,
                        left_col.current.width + e.delta_x,
                    ),
                )
                self.state.viewer.left_panel_width = int(new_width)
                left_col.current.width = new_width
                _safe_update(left_col.current)
        elif panel == "middle":
            mid_col = refs.get("mid_col")
            if mid_col and mid_col.current:
                new_width = max(
                    self.config.ui.panel_middle_min_width,
                    min(
                        self.config.ui.panel_middle_max_width,
                        mid_col.current.width + e.delta_x,
                    ),
                )
                self.state.viewer.middle_panel_width = int(new_width)
                mid_col.current.width = new_width
                _safe_update(mid_col.current)

    def on_panel_resize_end(self, e: ft.DragEndEvent | None, panel: str) -> None:
        if panel == "left":
            self.page.client_storage.set(
                "left_panel_width", self.state.viewer.left_panel_width
            )
        elif panel == "middle":
            self.page.client_storage.set(
                "middle_panel_width", self.state.viewer.middle_panel_width
            )

    def toggle_tab_panel(self, collapsed: bool | None = None) -> None:
        if collapsed is None:
            collapsed = not self.state.ui.tab_panel_collapsed
        self.state.ui.tab_panel_collapsed = collapsed

        self.page.client_storage.set("tab_panel_collapsed", collapsed)

        mid = refs.get("mid_col")
        handle = refs.get("middle_resize_handle_container")
        rail = refs.get("tab_expand_rail")
        if mid and mid.current:
            mid.current.visible = not collapsed
        if handle and handle.current:
            handle.current.visible = not collapsed
        if rail and rail.current:
            rail.current.visible = collapsed
        self.page.update()

    def on_page_tap(self, e: ft.ControlEvent) -> None:
        self.ui_gestures.on_page_tap(e)
