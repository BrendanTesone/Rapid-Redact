"""
Matches tab view - Search results with filtering and bulk redaction

NOTE: This file is intentionally NOT split. Match card building, list rendering,
filtering, and action handlers are tightly coupled through shared global controller
state, callbacks, and circular dependencies. Splitting would create import cycles.
The upcoming refactor (pure functions, remove global _controller) will improve structure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from src.core.state.app_state import SearchResult
from src.core.state.ui_state import refs
from src.ui.views import base_results_view

if TYPE_CHECKING:
    from src.controllers.main_controller import MainController

_controller: MainController | None = None


def _passes_results_filters(item: SearchResult, filter_text: str) -> bool:
    """Only shows MATCHES category. Within matches, applies dismiss and term filters."""
    from src.core.state.app_state import ResultCategory

    if item.category != ResultCategory.MATCHES:
        return False

    if not _controller:
        return True

    show_dismissed_ref = refs.get("chk_show_dismissed")
    show_dismissed = (
        show_dismissed_ref.current.value
        if show_dismissed_ref and show_dismissed_ref.current
        else False
    )
    if item.dismissed and not show_dismissed:
        return False

    term_filter = str(_controller.state.search.results_term_filter or "").strip()

    if (
        term_filter
        and term_filter not in ("all", "All Selected Terms")
        and item.term != term_filter
    ):
        return False

    return True


def render_text_results_list(filter_text: str = "") -> None:
    """Render the Matches (results) list using configurable renderer."""
    from src.core.state.app_state import ResultCategory

    config = base_results_view.ResultsListConfig(
        listview_ref="results_list",
        term_predicate=lambda r: r.category == ResultCategory.MATCHES,
        icon=ft.Icons.DESCRIPTION,
        icon_color="blue",
        dismiss_checkbox_ref="chk_show_dismissed",
        passes_filters_fn=_passes_results_filters,
        navigate_fn=navigate_to_match,
        toggle_fn=base_results_view.toggle_result_redaction_simple,
    )
    base_results_view.render_results_list(config, filter_text)


def navigate_to_match(
    file_name: str, file_path: str, page: int, highlight: str
) -> None:
    """Navigate to a match and show ALL highlights on that page.

    Calls navigate_to_page directly without setting current_term,
    ensuring all highlights on the page are visible simultaneously.
    """
    if not _controller:
        return
    _controller.viewer.navigate_to_page(file_path, page)


def build_view(controller: "MainController") -> ft.Container:
    """Build the Matches tab view with switchable File/Terms content."""
    global _controller
    _controller = controller
    base_results_view.register_controller(controller)

    if "btn_matches_file_view" not in refs:
        refs["btn_matches_file_view"] = ft.Ref[ft.ElevatedButton]()
    if "btn_matches_terms_view" not in refs:
        refs["btn_matches_terms_view"] = ft.Ref[ft.ElevatedButton]()
    if "matches_switchable_content" not in refs:
        refs["matches_switchable_content"] = ft.Ref[ft.Container]()
    if "matches_filters_container" not in refs:
        refs["matches_filters_container"] = ft.Ref[ft.Container]()

    def switch_to_file_view(_: ft.ControlEvent | None = None) -> None:
        """Switch to match results view."""
        content_container = refs["matches_switchable_content"].current
        if content_container:
            content_container.content = ft.ListView(
                ref=refs["results_list"], expand=True, spacing=5, item_extent=85
            )
            btn_file = refs["btn_matches_file_view"].current
            btn_terms = refs["btn_matches_terms_view"].current
            if btn_file:
                btn_file.bgcolor = "blue"
                btn_file.color = "white"
            if btn_terms:
                btn_terms.bgcolor = None
                btn_terms.color = None
            filters_container = refs.get("matches_filters_container")
            if filters_container and filters_container.current:
                filters_container.current.visible = True
            render_text_results_list()
            if controller.page:
                controller.page.update()

    def switch_to_terms_view(_: ft.ControlEvent | None = None) -> None:
        """Switch to terms view."""
        content_container = refs["matches_switchable_content"].current
        if content_container:
            content_container.content = ft.Column(
                [
                    ft.Row(
                        [
                            ft.TextField(
                                ref=refs["new_term_input"],
                                hint_text="Add term",
                                expand=True,
                                on_submit=controller.search_term.add_term,
                            ),
                            ft.IconButton(
                                "add", on_click=controller.search_term.add_term
                            ),
                        ]
                    ),
                    ft.Row(
                        [
                            ft.TextButton(
                                "Import",
                                icon=ft.Icons.UPLOAD_FILE,
                                tooltip="Import terms from Excel file",
                                on_click=controller.export.import_terms_from_excel,
                            ),
                            ft.TextButton(
                                "Export",
                                icon=ft.Icons.DOWNLOAD,
                                tooltip="Export terms to Excel file",
                                on_click=controller.export.export_terms_to_excel,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.DataTable(
                                    ref=refs["terms_table"],
                                    columns=[
                                        ft.DataColumn(ft.Text("On"), numeric=False),
                                        ft.DataColumn(ft.Text("Term"), numeric=False),
                                        ft.DataColumn(ft.Text("Del"), numeric=False),
                                    ],
                                    rows=[],
                                    width=float("inf"),
                                    column_spacing=10,
                                )
                            ],
                            scroll=ft.ScrollMode.AUTO,
                        ),
                        expand=True,
                        bgcolor="white",
                    ),
                ],
                scroll=ft.ScrollMode.AUTO,
            )
            btn_file = refs["btn_matches_file_view"].current
            btn_terms = refs["btn_matches_terms_view"].current
            if btn_file:
                btn_file.bgcolor = None
                btn_file.color = None
            if btn_terms:
                btn_terms.bgcolor = "blue"
                btn_terms.color = "white"
            filters_container = refs.get("matches_filters_container")
            if filters_container and filters_container.current:
                filters_container.current.visible = False
            controller.search_term.refresh_term_table()
            if controller.page:
                controller.page.update()

    return ft.Container(
        padding=5,
        content=ft.Column(
            [
                ft.ElevatedButton(
                    "SEARCH",
                    on_click=controller.search_execution.run_search,
                    bgcolor="blue",
                    color="white",
                    width=float("inf"),
                ),
                ft.ProgressBar(
                    ref=refs["matches_progress"],
                    visible=False,
                    width=float("inf"),
                ),
                ft.Divider(height=1),
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "File View",
                            ref=refs["btn_matches_file_view"],
                            on_click=switch_to_file_view,
                            bgcolor="blue",
                            color="white",
                            expand=True,
                        ),
                        ft.ElevatedButton(
                            "Terms",
                            ref=refs["btn_matches_terms_view"],
                            on_click=switch_to_terms_view,
                            expand=True,
                        ),
                    ],
                    spacing=8,
                ),
                ft.Divider(height=1),
                ft.Container(
                    ref=refs["matches_filters_container"],
                    visible=True,
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Dropdown(
                                        ref=refs["dd_results_term_filter"],
                                        label="Term",
                                        dense=True,
                                        expand=True,
                                        options=[
                                            ft.dropdown.Option("All Selected Terms")
                                        ],
                                        value="All Selected Terms",
                                        on_change=controller.search_results.on_results_term_filter_change,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                spacing=8,
                            ),
                            ft.Row(
                                [
                                    ft.Checkbox(
                                        ref=refs["chk_show_dismissed"],
                                        label="Show dismissed",
                                        value=False,
                                        on_change=controller.search_results.on_toggle_show_dismissed,
                                    ),
                                ],
                                spacing=8,
                            ),
                        ],
                        spacing=0,
                    ),
                ),
                ft.Container(
                    ref=refs["matches_switchable_content"],
                    content=ft.ListView(
                        ref=refs["results_list"], expand=True, spacing=5, item_extent=85
                    ),
                    expand=True,
                ),
            ]
        ),
    )
