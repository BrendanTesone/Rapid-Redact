"""
Consistency tab view - Detect text redacted in some places but not others
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
    show_dismissed_ref = refs.get("chk_consistency_show_dismissed")
    show_dismissed = (
        show_dismissed_ref.current.value
        if show_dismissed_ref and show_dismissed_ref.current
        else False
    )
    if item.dismissed and not show_dismissed:
        return False

    if not filter_text:
        return True

    hay = (item.file_name + item.match + item.context).lower()
    return filter_text.lower() in hay


def navigate_to_match(
    file_name: str, file_path: str, page: int, highlight: str
) -> None:
    """Navigate to consistency gap. Calls navigate_to_page directly without setting
    current_term, ensuring all highlights on the page are visible simultaneously."""
    if not _controller:
        return
    _controller.viewer.navigate_to_page(file_path, page)


def render_consistency_list(filter_text: str = "") -> None:
    if not _controller:
        return

    from src.core.state.app_state import ResultCategory

    config = base_results_view.ResultsListConfig(
        listview_ref="consistency_list",
        term_predicate=lambda r: r.category == ResultCategory.GAP,
        icon=ft.Icons.ERROR,
        icon_color="#D32F2F",
        dismiss_checkbox_ref="chk_consistency_show_dismissed",
        passes_filters_fn=_passes_results_filters,
        navigate_fn=navigate_to_match,
        toggle_fn=base_results_view.toggle_result_redaction_simple,
    )
    base_results_view.render_results_list(config, filter_text)


def build_view(controller: "MainController") -> ft.Container:
    """Build the Consistency check tab view.

    Consistency scans run automatically in the background when redactions change.
    The manual button forces an immediate re-scan.
    """
    global _controller
    _controller = controller
    base_results_view.register_controller(controller)

    if "consistency_list" not in refs:
        refs["consistency_list"] = ft.Ref[ft.ListView]()
    if "btn_consistency_scan" not in refs:
        refs["btn_consistency_scan"] = ft.Ref[ft.ElevatedButton]()
    if "chk_consistency_show_dismissed" not in refs:
        refs["chk_consistency_show_dismissed"] = ft.Ref[ft.Checkbox]()

    return ft.Container(
        padding=10,
        content=ft.Column(
            [
                ft.ElevatedButton(
                    ref=refs["btn_consistency_scan"],
                    text="Scan Now",
                    icon="refresh",
                    bgcolor="#1565C0",
                    color="white",
                    on_click=controller.consistency.run_deep_consistency_scan,
                    tooltip="Run consistency scan",
                    width=float("inf"),
                ),
                ft.Divider(height=1, color="#D32F2F"),
                ft.Row(
                    [
                        ft.Checkbox(
                            ref=refs["chk_consistency_show_dismissed"],
                            label="Show dismissed",
                            value=False,
                            on_change=lambda _: render_consistency_list(),
                        ),
                    ],
                    spacing=8,
                ),
                ft.ListView(
                    ref=refs["consistency_list"], expand=True, spacing=5, item_extent=85
                ),
            ],
            spacing=6,
        ),
    )
