"""
Dose tab view - displays dosage search results with filtering.

NOTE: Intentionally not split. Match card building, list rendering, filtering,
and action handlers are tightly coupled through shared global controller state
and callbacks. Splitting would create import cycles without improving clarity.
The upcoming Priority 2.1 refactor (pure functions, remove global _controller)
will improve structure without splitting.
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
    """Only shows DOSAGE category items. Within dosage, applies dismiss filter.

    Does not apply results_term_filter - the term_predicate already handles
    filtering. Dose tab shows all dose results regardless of matches tab filter.
    """
    from src.core.state.app_state import ResultCategory

    if item.category != ResultCategory.DOSAGE:
        return False

    show_dismissed_ref = refs.get("chk_dose_show_dismissed")
    show_dismissed = (
        show_dismissed_ref.current.value
        if show_dismissed_ref and show_dismissed_ref.current
        else False
    )
    if item.dismissed and not show_dismissed:
        return False

    return True


def render_dose_results_list(filter_text: str = "") -> None:
    from src.core.state.app_state import ResultCategory

    config = base_results_view.ResultsListConfig(
        listview_ref="dose_results_list",
        term_predicate=lambda r: r.category == ResultCategory.DOSAGE,
        icon=ft.Icons.MEDICAL_SERVICES,
        icon_color="#FF6F00",
        dismiss_checkbox_ref="chk_dose_show_dismissed",
        passes_filters_fn=_passes_results_filters,
        navigate_fn=navigate_to_match,
        toggle_fn=base_results_view.toggle_result_redaction_simple,
    )
    base_results_view.render_results_list(config, filter_text)


def navigate_to_match(
    file_name: str, file_path: str, page: int, highlight: str
) -> None:
    """Navigate to a match and show all dose highlights on the page.

    Calls navigate_to_page without setting current_term to ensure all
    highlights on the page are visible simultaneously.
    """
    if not _controller:
        return
    _controller.viewer.navigate_to_page(file_path, page)


def build_view(controller: MainController) -> ft.Container:
    global _controller
    _controller = controller
    base_results_view.register_controller(controller)

    if "dose_results_list" not in refs:
        refs["dose_results_list"] = ft.Ref[ft.ListView]()
    if "chk_dose_show_dismissed" not in refs:
        refs["chk_dose_show_dismissed"] = ft.Ref[ft.Checkbox]()

    return ft.Container(
        padding=5,
        content=ft.Column(
            [
                ft.ElevatedButton(
                    "SCAN FOR DOSES",
                    on_click=lambda _: controller.dose.run_dose_scan(),
                    bgcolor="#FF6F00",
                    color="white",
                    width=float("inf"),
                ),
                ft.ProgressBar(
                    ref=refs["dose_progress"],
                    visible=False,
                    width=float("inf"),
                ),
                ft.Divider(height=1, color="#FF6F00"),
                ft.Row(
                    [
                        ft.Checkbox(
                            ref=refs["chk_dose_show_dismissed"],
                            label="Show dismissed",
                            value=False,
                            on_change=controller.search_results.on_toggle_show_dismissed,
                        ),
                    ],
                    spacing=8,
                ),
                ft.ListView(
                    ref=refs["dose_results_list"],
                    expand=True,
                    spacing=5,
                    item_extent=85,
                ),
            ]
        ),
    )
