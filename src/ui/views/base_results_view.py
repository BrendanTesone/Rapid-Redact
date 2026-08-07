"""Shared functionality for Matches and Dose result views."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import flet as ft

from src.core.state.app_state import RedactionBox, ResultCategory, SearchResult
from src.core.state.ui_state import refs
from src.ui.components.result_cards import (
    ActionButton,
    Badge,
    HighlightedText,
    build_action_button,
    build_badge,
    build_highlighted_spans,
)

if TYPE_CHECKING:
    from src.controllers.main_controller import MainController


@dataclass
class ResultsListConfig:
    """Configuration for rendering a results list."""

    listview_ref: str
    term_predicate: Callable[[SearchResult], bool]
    icon: str
    icon_color: str
    dismiss_checkbox_ref: str
    passes_filters_fn: Callable[[SearchResult, str], bool]
    navigate_fn: Callable[[str, str, int, str], None]
    toggle_fn: Callable[[SearchResult], None]


_controller: MainController | None = None


def register_controller(ctrl: MainController) -> None:
    """Store a reference to the MainController for dismiss/restore calls."""
    global _controller
    _controller = ctrl
def build_match_card(
    it: SearchResult,
    navigate_fn: Callable[[str, str, int, str], None],
    toggle_fn: Callable[[SearchResult], None] | None = None,
) -> ft.Control:
    """Build a single result card control for a match item."""
    highlighted = HighlightedText(full_text=it.context, highlight=it.match or "")
    spans = build_highlighted_spans(highlighted)

    is_redacted = it.redacted
    is_dismissed = it.dismissed
    highlight_text = it.match

    it_file_path = it.file_path
    it_page = it.page
    it_term_for_viewer = highlight_text

    action_buttons: list[ft.Control] = []

    def _on_restore(e: ft.ControlEvent, item: SearchResult = it) -> None:
        if _controller:
            _controller.search_results.restore_match(item)

    def _on_redact(e: ft.ControlEvent, item: SearchResult = it) -> None:
        if toggle_fn:
            toggle_fn(item)

    def _on_dismiss(e: ft.ControlEvent, item: SearchResult = it) -> None:
        if _controller:
            _controller.search_results.dismiss_match(item)

    if is_dismissed:
        action_buttons.append(
            build_action_button(
                ActionButton(
                    label="Restore",
                    bgcolor="blue",
                    on_click=_on_restore,
                    tooltip="Remove false-positive dismissal",
                )
            )
        )
    else:
        action_buttons.append(
            build_action_button(
                ActionButton(
                    label="Un-Redact" if is_redacted else "Redact",
                    bgcolor="green" if is_redacted else "red",
                    on_click=_on_redact,
                )
            )
        )
        if not is_redacted:
            action_buttons.append(
                build_action_button(
                    ActionButton(
                        label="Dismiss",
                        bgcolor="grey600",
                        on_click=_on_dismiss,
                        tooltip="Mark as false positive (not a redaction target)",
                    )
                )
            )

    if is_dismissed:
        card_bg = "#f5f5f5"
        text_color = "grey"
    elif is_redacted:
        card_bg = "#e0e0e0"
        text_color = "grey"
    elif it.category == ResultCategory.DOSAGE:
        card_bg = "#FFE6CC"
        text_color = "black"
    else:
        card_bg = "grey50"
        text_color = "black"

    return ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        f"Pg {it.page}",
                                        weight="bold",
                                        color=(
                                            "#1565C0" if not is_dismissed else "grey700"
                                        ),
                                        size=12,
                                    ),
                                ]
                                + (
                                    [
                                        ft.Text(
                                            f"({it.term})",
                                            italic=True,
                                            size=11,
                                            color=(
                                                "#1565C0"
                                                if not is_dismissed
                                                else "grey700"
                                            ),
                                        ),
                                    ]
                                    if it.term
                                    else []
                                )
                                + (
                                    [
                                        build_badge(
                                            Badge(
                                                text="DISMISSED",
                                                bgcolor="grey700",
                                                size=8,
                                            )
                                        )
                                    ]
                                    if is_dismissed
                                    else []
                                ),
                                spacing=6,
                            ),
                            ft.Row(action_buttons, spacing=4),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    bgcolor="#E3F2FD" if not is_dismissed else "#F5F5F5",
                    padding=ft.padding.symmetric(horizontal=10, vertical=6),
                ),
                ft.Container(
                    content=ft.Text(
                        spans=spans,
                        size=12,
                        color=text_color,
                    ),
                    padding=ft.padding.all(10),
                    bgcolor=card_bg,
                ),
            ],
            spacing=0,
        ),
        border=ft.border.all(
            1,
            "grey400" if is_dismissed else "grey300",
        ),
        border_radius=6,
        margin=ft.margin.only(bottom=8),
        on_click=(
            lambda _, f=it_file_path, p=it_page, t=it_term_for_viewer, fn=it.file_name: (
                navigate_fn(fn, f, p, t) if _controller else None
            )
        ),
    )


def navigate_to_result(
    controller: MainController,
    file_name: str,
    file_path: str,
    page: int,
    highlight: str,
    highlight_behavior: str = "default",
) -> None:
    """Unified navigation for all result types.

    highlight_behavior options:
        - "default" or "all_terms": Clear current_term to show all highlights
        - "force_term": Set current_term to highlight for specialized filtering
    """
    if not controller:
        return

    if highlight_behavior == "all_terms" or highlight_behavior == "default":
        controller.state.search.current_term = ""
    elif highlight_behavior == "force_term":
        controller.state.search.current_term = highlight

    controller.viewer.navigate_to_page(file_path, page)


def _prepare_redaction_data(
    item: SearchResult,
) -> tuple[str, int, list[RedactionBox], str] | None:
    """Prepare redaction data for a single SearchResult without mutating state."""
    fname = item.file_name
    page_idx = item.page - 1
    rects = item.rects

    if not rects or not fname:
        return None

    batch_id = str(uuid.uuid4())

    from src.core.state.app_state import SelectionMode
    from src.core.domain.toc_util import get_section_title_for_page

    section_title = get_section_title_for_page(item.file_path, item.page)

    boxes = [
        RedactionBox(
            id=str(uuid.uuid4()),
            x=rect.x,
            y=rect.y,
            w=rect.w,
            h=rect.h,
            page=page_idx,
            selection_mode=SelectionMode.HIGHLIGHT,
            batch_id=batch_id,
            match=item.match,
            term=item.term,
            section_title=section_title,
        )
        for rect in rects
    ]

    return (fname, page_idx, boxes, batch_id)


def add_result_redaction(item: SearchResult) -> None:
    """Add redaction for a single match result."""
    if not _controller:
        return

    redaction_data = _prepare_redaction_data(item)
    if redaction_data is None:
        _controller.page.open(
            ft.SnackBar(
                ft.Text(
                    "Could not find coordinates for this match. Try searching again."
                ),
                bgcolor="orange",
            )
        )
        return

    fname, page_idx, boxes, batch_id = redaction_data

    _controller.redaction_data.add_redaction_batch(boxes, page_idx, fname)

    for search_result in _controller.state.search.all_search_results:
        if search_result.id == item.id:
            search_result.redacted = True
            search_result.batch_id = batch_id
            break

    if not _try_smart_tile_update(fname, item.category):
        _refresh_results_list_by_category(item.category)

    _controller.viewer.navigate_to_page(
        _controller.state.viewer.file_path or "",
        _controller.state.viewer.page_index + 1,
    )


def toggle_result_redaction_simple(item: SearchResult) -> None:
    """Standard toggle redaction for match/dose/AI results.

    Use this for views that don't have custom gap-level logic.
    """
    if item.redacted:
        remove_result_redaction(item)
    else:
        add_result_redaction(item)


def remove_result_redaction(item: SearchResult) -> None:
    """Remove redaction for a single match result."""
    if not _controller:
        return

    fname = item.file_name
    batch_id = item.batch_id

    if batch_id and fname:
        _controller.redaction_data.remove_batch_redaction(fname, batch_id)

    for result in _controller.state.search.all_search_results:
        if result.id == item.id:
            result.redacted = False
            result.batch_id = ""
            break

    if not _try_smart_tile_update(fname, item.category):
        _refresh_results_list_by_category(item.category)

    _controller.viewer.navigate_to_page(
        _controller.state.viewer.file_path or "",
        _controller.state.viewer.page_index + 1,
    )


def _refresh_results_list_by_category(category: ResultCategory) -> None:
    """Refresh the appropriate results list based on category."""
    if category == ResultCategory.DOSAGE:
        from src.ui.views import dose_view

        dose_view.render_dose_results_list()
    elif category == ResultCategory.MATCHES:
        from src.ui.views import matches_view

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
    elif category == ResultCategory.PD_CHECKER:
        from src.ui.views import pd_checker_view

        pd_checker_view.refresh_pd_checker_results()


def _toggle_all_in_file(
    items: list[SearchResult], toggle_fn: Callable[[SearchResult], None]
) -> None:
    """Toggle redaction for all items in a file.

    If any items are unredacted, redact all unredacted items in batch.
    If all items are redacted, un-redact all items in batch.
    """
    if not items or not _controller:
        return

    loading_overlay = refs.get("viewer_loading_overlay")
    if loading_overlay and loading_overlay.current:
        loading_overlay.current.visible = True
        _controller.page.update()

    try:
        has_unredacted = any(not item.redacted for item in items)

        if has_unredacted:
            items_to_redact = [item for item in items if not item.redacted]

            if not items_to_redact:
                return

            all_redaction_data = []
            for item in items_to_redact:
                redaction_data = _prepare_redaction_data(item)
                if redaction_data is not None:
                    all_redaction_data.append((item, redaction_data))

            if not all_redaction_data:
                return

            for item, (fname, page_idx, boxes, batch_id) in all_redaction_data:
                _controller.redaction_data.add_redaction_batch(boxes, page_idx, fname)

            batch_id_map = {item.id: data[3] for item, data in all_redaction_data}
            for search_result in _controller.state.search.all_search_results:
                if search_result.id in batch_id_map:
                    search_result.redacted = True
                    search_result.batch_id = batch_id_map[search_result.id]

            fname = items_to_redact[0].file_name
            category = items_to_redact[0].category
            if not _try_smart_tile_update(fname, category):
                _refresh_results_list_by_category(category)

            _controller.viewer.navigate_to_page(
                _controller.state.viewer.file_path or "",
                _controller.state.viewer.page_index + 1,
            )
        else:
            items_to_unredact = [item for item in items if item.redacted]

            if not items_to_unredact:
                return

            fname = items_to_unredact[0].file_name

            batch_ids_to_remove = set()
            box_ids_to_remove = []
            for item in items_to_unredact:
                if item.batch_id:
                    batch_ids_to_remove.add(item.batch_id)
                else:
                    box_ids_to_remove.append(item.id)

            for batch_id in batch_ids_to_remove:
                _controller.redaction_data.remove_batch_redaction(fname, batch_id)

            for box_id in box_ids_to_remove:
                _controller.redaction_data.remove_redaction_by_id(fname, box_id)

            items_to_unredact_ids = {item.id for item in items_to_unredact}
            for search_result in _controller.state.search.all_search_results:
                if search_result.id in items_to_unredact_ids:
                    search_result.redacted = False
                    search_result.batch_id = ""

            category = items_to_unredact[0].category
            if not _try_smart_tile_update(fname, category):
                _refresh_results_list_by_category(category)

            _controller.viewer.navigate_to_page(
                _controller.state.viewer.file_path or "",
                _controller.state.viewer.page_index + 1,
            )
    finally:
        if loading_overlay and loading_overlay.current:
            loading_overlay.current.visible = False
            _controller.page.update()


def _build_file_expansion_tile(
    file_name: str,
    items: list[SearchResult],
    selected_name_to_path: dict[str, str],
    config: ResultsListConfig,
) -> ft.ExpansionTile:
    """Build ExpansionTile for a single file."""
    if items:
        full_path = items[0].file_path
    else:
        full_path = selected_name_to_path.get(file_name, "")

    active_items = [i for i in items if not i.dismissed]
    all_redacted = all(i.redacted for i in active_items) if active_items else False
    button_label = "Un-Redact All" if all_redacted else "Redact All"
    redact_btn_disabled = not bool(active_items)

    dismissed_count = sum(1 for i in items if i.dismissed)
    match_label = f"{len(items)} matches" if items else "0 matches"
    if dismissed_count > 0:
        match_label += f", {dismissed_count} dismissed"

    header_content = ft.Row(
        [
            ft.Column(
                [
                    ft.Text(
                        file_name,
                        weight="bold",
                        size=14,
                        width=180,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(
                        match_label,
                        size=11,
                        color="grey",
                    ),
                ],
                spacing=2,
            ),
            ft.Container(
                content=ft.Text(
                    button_label,
                    size=10,
                    weight="bold",
                    color="green" if all_redacted else "red",
                ),
                border=ft.border.all(1, "green" if all_redacted else "red"),
                border_radius=4,
                padding=4,
                opacity=0.3 if redact_btn_disabled else 1.0,
                tooltip=(
                    "No matches to redact."
                    if redact_btn_disabled
                    else "Applies to the currently filtered non-dismissed matches for this file."
                ),
                on_click=(
                    None
                    if redact_btn_disabled
                    else lambda e, items=active_items, toggle_fn=config.toggle_fn: (
                        _toggle_all_in_file(items, toggle_fn)
                    )
                ),
            ),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        width=330,
    )

    file_controls: list[ft.Control] = []

    if items:
        for it in items:
            file_controls.append(
                build_match_card(it, config.navigate_fn, config.toggle_fn)
            )
    else:
        file_controls.append(
            ft.Text(
                "No matches in this file (current filters).",
                italic=True,
                color="grey",
            )
        )

    is_expanded = file_name in (
        _controller.state.ui.expanded_files if _controller else set()
    )

    def on_tile_change(e: ft.ControlEvent, f: str, p: str) -> None:
        if not _controller:
            return
        if e.data == "true":
            _controller.state.ui.expanded_files.add(f)
            current_file = _controller.state.viewer.file_path
            if current_file != p and p:
                _controller.viewer.navigate_to_page(p, 1)
        else:
            _controller.state.ui.expanded_files.discard(f)

    return ft.ExpansionTile(
        title=header_content,
        controls=file_controls,
        leading=ft.Icon(config.icon, color=config.icon_color),
        initially_expanded=is_expanded,
        on_change=(lambda e, f=file_name, p=full_path: on_tile_change(e, f, p)),
        data={"file_name": file_name},
    )


def _update_file_tile(
    lv: ft.ListView,
    file_name: str,
    config: ResultsListConfig,
    filter_text: str,
) -> bool:
    """Update only the ExpansionTile for the specified file.

    Returns True if tile was found and updated, False if full render is needed.
    """
    if not _controller:
        return False

    tile_index = None
    for i, control in enumerate(lv.controls):
        if isinstance(control, ft.ExpansionTile):
            tile_data = getattr(control, "data", None)
            if isinstance(tile_data, dict) and tile_data.get("file_name") == file_name:
                tile_index = i
                break

    if tile_index is None:
        return False

    all_results = _controller.state.search.all_search_results
    selected_paths = _controller.state.project.file_list
    selected_name_to_path: dict[str, str] = {}
    for p in selected_paths:
        if isinstance(p, str) and p.lower().endswith(".pdf") and os.path.exists(p):
            selected_name_to_path[os.path.basename(p)] = p

    file_items = [
        r
        for r in all_results
        if r.file_name == file_name
        and config.term_predicate(r)
        and config.passes_filters_fn(r, filter_text)
    ]

    file_items.sort(key=lambda r: (r.page, r.rects[0].y if r.rects else 0))

    new_tile = _build_file_expansion_tile(
        file_name, file_items, selected_name_to_path, config
    )

    lv.controls[tile_index] = new_tile
    if lv.page:
        lv.update()
    else:
        if _controller and _controller.page:
            _controller.page.update()

    return True


def _try_smart_tile_update(file_name: str, category: "ResultCategory") -> bool:
    """Try to update only the affected file's tile instead of full render.

    Returns True if smart update succeeded, False if full render is needed.
    """
    from src.core.state.app_state import ResultCategory

    if not _controller:
        return False

    if category == ResultCategory.DOSAGE:
        from src.ui.views import dose_view
        from src.ui.views.dose_view import _passes_results_filters

        listview_ref = "dose_results_list"

        def term_predicate(r: SearchResult) -> bool:
            return r.category == ResultCategory.DOSAGE

        passes_filters_fn = _passes_results_filters
        icon = ft.Icons.MEDICAL_SERVICES
        icon_color = "#FF6F00"

        def navigate_fn(
            file_name: str, file_path: str, page: int, highlight: str
        ) -> None:
            dose_view.navigate_to_match(file_name, file_path, page, highlight)

        def toggle_fn(item: SearchResult) -> None:
            toggle_result_redaction_simple(item)

    elif category == ResultCategory.AI:
        from src.ui.views import ai_detection_view
        from src.ui.views.ai_detection_view import _passes_ai_filters

        listview_ref = "ai_detections_list"

        def term_predicate(r: SearchResult) -> bool:
            return r.category == ResultCategory.AI

        def passes_filters_fn(item: SearchResult, filter_text: str) -> bool:
            return _passes_ai_filters(item, filter_text)

        icon = ft.Icons.PSYCHOLOGY
        icon_color = "purple"

        def navigate_fn(
            file_name: str, file_path: str, page: int, highlight: str
        ) -> None:
            ai_detection_view._navigate_to_ai_match(
                file_name, file_path, page, highlight
            )

        def toggle_fn(item: SearchResult) -> None:
            toggle_result_redaction_simple(item)

    elif category == ResultCategory.GAP:
        return False

    else:
        from src.ui.views import matches_view
        from src.ui.views.matches_view import _passes_results_filters

        listview_ref = "results_list"

        def term_predicate(r: SearchResult) -> bool:
            return r.category == ResultCategory.MATCHES

        passes_filters_fn = _passes_results_filters
        icon = ft.Icons.DESCRIPTION
        icon_color = "blue"

        def navigate_fn(
            file_name: str, file_path: str, page: int, highlight: str
        ) -> None:
            matches_view.navigate_to_match(file_name, file_path, page, highlight)

        def toggle_fn(item: SearchResult) -> None:
            toggle_result_redaction_simple(item)

    lv_ref = refs.get(listview_ref)
    if not lv_ref or not lv_ref.current:
        return False

    lv = lv_ref.current
    filter_text = getattr(lv, "data", "") or ""

    config = ResultsListConfig(
        listview_ref=listview_ref,
        term_predicate=term_predicate,
        icon=icon,
        icon_color=icon_color,
        dismiss_checkbox_ref="",
        passes_filters_fn=passes_filters_fn,
        navigate_fn=navigate_fn,
        toggle_fn=toggle_fn,
    )

    return _update_file_tile(lv, file_name, config, filter_text)


def render_results_list(config: ResultsListConfig, filter_text: str = "") -> None:
    """Generic results list renderer."""
    lv_ref = refs.get(config.listview_ref)
    if not lv_ref or not lv_ref.current:
        return
    lv = lv_ref.current
    lv.data = filter_text
    lv.controls.clear()

    all_results = _controller.state.search.all_search_results if _controller else []

    selected_paths = _controller.state.project.file_list if _controller else []
    selected_name_to_path: dict[str, str] = {}
    for p in selected_paths:
        if isinstance(p, str) and p.lower().endswith(".pdf") and os.path.exists(p):
            selected_name_to_path[os.path.basename(p)] = p

    grouped: dict[str, list[SearchResult]] = {}
    if selected_name_to_path:
        grouped = {name: [] for name in selected_name_to_path.keys()}

    for item in all_results:
        if not config.term_predicate(item):
            continue
        if not config.passes_filters_fn(item, filter_text):
            continue
        if not item.file_name:
            continue
        grouped.setdefault(item.file_name, []).append(item)

    if not grouped:
        lv.controls.append(ft.Text("No matches found.", italic=True, color="grey"))
        if lv.page:
            lv.update()
        return

    for file_name in sorted(grouped.keys()):
        items = grouped[file_name]
        items.sort(key=lambda r: (r.page, r.rects[0].y if r.rects else 0))

        tile = _build_file_expansion_tile(
            file_name, items, selected_name_to_path, config
        )
        lv.controls.append(tile)

    if lv.page:
        lv.update()
