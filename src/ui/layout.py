"""Application layout construction."""

from __future__ import annotations

# TYPE_CHECKING required to break circular import: main_controller <-> ui_layout
from typing import TYPE_CHECKING

import flet as ft

from src.core.state.ui_state import refs
from src.ui.views import (
    ai_detection_view,
    bookmarks_view,
    consistency_view,
    dose_view,
    files_view,
    matches_view,
    pd_checker_view,
    terms_view,
    viewer_view,
)
from src.ui.views.amendment import amendment_transfer_view
from src.ui.radial_mode_selector import create_radial_selector

if TYPE_CHECKING:
    from src.controllers.main_controller import MainController


def _build_resize_handle(controller: MainController, panel: str) -> ft.GestureDetector:
    kwargs = {}
    if panel == "middle":
        kwargs["ref"] = refs["middle_resize_handle_container"]
    return ft.GestureDetector(
        content=ft.Container(
            width=8,
            bgcolor="grey300",
            border_radius=2,
        ),
        on_horizontal_drag_update=lambda e: controller.on_panel_resize(e, panel),
        on_horizontal_drag_end=lambda e: controller.on_panel_resize_end(e, panel),
        **kwargs,
    )


def build_view_text_matches(controller: MainController) -> ft.Container:
    return matches_view.build_view(controller)


def build_view_bookmarks(controller: MainController) -> ft.Container:
    return bookmarks_view.build_view(controller)


def build_view_consistency(controller: MainController) -> ft.Container:
    return consistency_view.build_view(controller)


def build_view_viewer(controller: MainController) -> ft.Container:
    return viewer_view.build_view(controller)


def build_view_files(controller: MainController) -> ft.Container:
    return files_view.build_view(controller)


def build_view_terms(controller: MainController) -> ft.Container:
    return terms_view.build_view(controller)


def build_view_dose(controller: MainController) -> ft.Container:
    return dose_view.build_view(controller)


def build_view_ai_detect(controller: MainController) -> ft.Container:
    return ai_detection_view.build_view(controller.ai_detection)


def build_view_amendment_transfer(controller: MainController) -> ft.Container:
    return amendment_transfer_view.build_view(controller)


def build_view_pd_checker(controller: MainController) -> ft.Container:
    pd_checker_view.register_ai_controller(controller.ai_detection)
    return pd_checker_view.build_view(controller)


def build_layout(controller: MainController) -> ft.Control:
    page = controller.page

    folder_picker = ft.FilePicker(on_result=controller.project_persistence.save_folder)
    controller._folder_picker = folder_picker
    page.overlay.append(folder_picker)
    page.overlay.append(controller.export._batch_save_folder_picker)

    view_viewer = build_view_viewer(controller)

    # Build views for side effects (ref registration); switch_tab swaps them in.
    build_view_files(controller)
    build_view_text_matches(controller)
    build_view_bookmarks(controller)
    build_view_dose(controller)
    build_view_consistency(controller)
    build_view_ai_detect(controller)
    build_view_amendment_transfer(controller)
    build_view_pd_checker(controller)

    middle_column = ft.Container(
        ref=refs["mid_col"],
        width=460,
        bgcolor="white",
        border=ft.border.symmetric(horizontal=ft.border.BorderSide(1, "grey300")),
        content=ft.Column(
            [
                ft.Container(
                    bgcolor="grey100",
                    padding=5,
                    content=ft.Row(
                        [
                            create_radial_selector(
                                modes=[
                                    ("amendment_transfer", "Amend"),
                                    ("ai_detect", "AI"),
                                    ("consistency", "Gap"),
                                    ("dose", "Dose"),
                                    ("matches", "Matches"),
                                    ("files", "Project"),
                                    ("viewer", "Viewer"),
                                ],
                                on_mode_change=lambda mode_key: controller.switch_tab(
                                    None, mode_key
                                ),
                                initial_mode="viewer",
                            ),
                            ft.Container(expand=True),
                            ft.IconButton(
                                ft.Icons.CHEVRON_LEFT,
                                ref=refs["btn_tab_collapse"],
                                tooltip="Collapse panel",
                                icon_size=14,
                                on_click=lambda _: controller.toggle_tab_panel(),
                                style=ft.ButtonStyle(
                                    padding=ft.padding.all(2),
                                ),
                            ),
                        ],
                        spacing=10,
                        tight=True,
                    ),
                ),
                ft.Container(
                    ref=refs["tab_content_area"],
                    content=view_viewer,
                    expand=True,
                ),
            ]
        ),
    )

    page_strip_vertical = ft.Container(
        width=36,
        bgcolor="grey200",
        border_radius=6,
        padding=ft.padding.symmetric(vertical=4, horizontal=2),
        content=ft.Column(
            ref=refs["page_strip_row"],
            controls=[],
            scroll=ft.ScrollMode.AUTO,
            spacing=2,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    vertical_toolbar = ft.Container(
        width=56,
        bgcolor="grey200",
        border_radius=8,
        padding=ft.padding.symmetric(vertical=2, horizontal=2),
        content=ft.Column(
            [
                ft.IconButton(
                    "keyboard_arrow_up",
                    tooltip="Previous page",
                    on_click=lambda _: controller.viewer.change_page(-1),
                    icon_size=14,
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.TextField(
                                ref=refs["page_num_txt"],
                                width=44,
                                height=24,
                                text_align="center",
                                text_size=9,
                                on_submit=controller.viewer.go_to_page_direct,
                                content_padding=ft.padding.all(1),
                            ),
                            ft.Text(
                                "0",
                                ref=refs["total_pages_lbl"],
                                size=8,
                                color="grey",
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        spacing=0,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    bgcolor="white",
                    border_radius=4,
                    padding=1,
                ),
                ft.IconButton(
                    "keyboard_arrow_down",
                    tooltip="Next page",
                    on_click=lambda _: controller.viewer.change_page(1),
                    icon_size=14,
                ),
                ft.Divider(height=2, color="grey400"),
                ft.IconButton(
                    ft.Icons.CROP_SQUARE,
                    ref=refs["btn_mode_rect_single"],
                    icon_color="blue",
                    tooltip="Rectangle (single)",
                    on_click=lambda _: controller.ui_gestures.set_mode("rect_single"),
                    icon_size=14,
                ),
                ft.IconButton(
                    ft.Icons.COPY_ALL,
                    ref=refs["btn_mode_rect_repeat"],
                    icon_color="grey",
                    tooltip="Rectangle (repeat)",
                    on_click=lambda _: controller.ui_gestures.set_mode("rect_repeat"),
                    icon_size=14,
                ),
                ft.IconButton(
                    ft.Icons.TEXT_FIELDS,
                    ref=refs["btn_mode_highlight_redact"],
                    icon_color="grey",
                    tooltip="Highlight + Redact",
                    on_click=lambda _: controller.ui_gestures.set_mode(
                        "highlight_redact"
                    ),
                    icon_size=14,
                ),
                ft.IconButton(
                    ft.Icons.FLASHLIGHT_ON,
                    ref=refs["btn_mode_highlight_only"],
                    icon_color="grey",
                    tooltip="Highlight Only (no redaction)",
                    on_click=lambda _: controller.ui_gestures.set_mode(
                        "highlight_only"
                    ),
                    icon_size=14,
                ),
                ft.Divider(height=2, color="grey400"),
                ft.IconButton(
                    ft.Icons.UNDO,
                    ref=refs["btn_undo"],
                    tooltip="Undo (Ctrl+Z)",
                    on_click=lambda _: controller.redaction_data.undo(),
                    icon_size=14,
                    disabled=True,
                ),
                ft.IconButton(
                    ft.Icons.REDO,
                    ref=refs["btn_redo"],
                    tooltip="Redo (Ctrl+Y)",
                    on_click=lambda _: controller.redaction_data.redo(),
                    icon_size=14,
                    disabled=True,
                ),
                ft.Text(
                    "",
                    ref=refs["undo_redo_label"],
                    size=7,
                    color="grey",
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Divider(height=2, color="grey400"),
                ft.IconButton(
                    ft.Icons.SELECT_ALL,
                    tooltip="Select all (Ctrl+A)",
                    on_click=lambda _: controller.redaction_interaction.select_all_annotations_on_page(),
                    icon_size=14,
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    icon_color="red",
                    tooltip="Delete (Del)",
                    on_click=lambda _: controller.redaction_interaction.delete_selected_annotations(),
                    icon_size=14,
                ),
                ft.Divider(height=2, color="grey400"),
                ft.IconButton(
                    "add",
                    tooltip="Zoom in",
                    on_click=lambda _: controller.viewer.change_zoom(0.25),
                    icon_size=14,
                ),
                ft.Text(
                    "100%",
                    ref=refs["zoom_lbl"],
                    size=9,
                    text_align=ft.TextAlign.CENTER,
                    width=44,
                ),
                ft.IconButton(
                    "remove",
                    tooltip="Zoom out",
                    on_click=lambda _: controller.viewer.change_zoom(-0.25),
                    icon_size=14,
                ),
                ft.IconButton(
                    ft.Icons.BOOKMARK_OUTLINE,
                    tooltip="Bookmarks",
                    on_click=lambda _: controller.bookmark.toggle_bookmarks_panel(),
                    icon_size=14,
                ),
                ft.Divider(height=2, color="grey400"),
                ft.IconButton(
                    ft.Icons.HELP_OUTLINE,
                    tooltip="Help (F1)",
                    on_click=lambda _: controller._show_shortcuts_dialog(),
                    icon_size=14,
                ),
            ],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO,
        ),
    )

    scrollable_viewer = ft.Container(
        content=ft.Row(
            [
                ft.Column(
                    [],
                    ref=refs["viewer_scroll_col"],
                    scroll=ft.ScrollMode.HIDDEN,
                    on_scroll=lambda e: controller.viewer.on_viewer_scroll(e),
                    spacing=12,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                )
            ],
            scroll=ft.ScrollMode.AUTO,
            alignment=ft.MainAxisAlignment.START,
        ),
        expand=True,
        bgcolor="#E0E0E0",
        border_radius=4,
    )

    bookmarks_overlay = ft.Container(
        ref=refs["bookmarks_overlay"],
        visible=False,
        width=350,
        bgcolor="white",
        border=ft.border.all(2, "grey400"),
        border_radius=8,
        padding=0,
        right=10,
        top=10,
        bottom=10,
        shadow=ft.BoxShadow(
            spread_radius=1,
            blur_radius=15,
            color="black,0.3",
        ),
        content=ft.Column(
            [
                ft.Container(
                    bgcolor="grey200",
                    padding=ft.padding.symmetric(horizontal=10, vertical=8),
                    content=ft.Row(
                        [
                            ft.IconButton(
                                ft.Icons.CLOSE,
                                icon_size=14,
                                tooltip="Close",
                                on_click=lambda _: controller.bookmark.toggle_bookmarks_panel(),
                            ),
                            ft.Text("Bookmarks", size=14, weight=ft.FontWeight.BOLD),
                        ],
                        spacing=4,
                    ),
                ),
                ft.Container(
                    content=ft.ListView(
                        ref=refs["bookmarks_list"],
                        controls=[],
                        expand=True,
                        spacing=0,
                        padding=4,
                    ),
                    expand=True,
                ),
            ],
            spacing=0,
        ),
    )

    viewer_loading_overlay = ft.Container(
        ref=refs["viewer_loading_overlay"],
        visible=False,
        alignment=ft.alignment.center,
        content=ft.Container(
            bgcolor="white",
            padding=20,
            border_radius=8,
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=10,
                color="black,0.25",
            ),
            content=ft.Row(
                [
                    ft.ProgressRing(width=24, height=24, stroke_width=3),
                    ft.Text("Loading PDF...", size=13),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=12,
                tight=True,
            ),
        ),
    )

    right_column = ft.Container(
        expand=True,
        bgcolor="grey100",
        padding=10,
        content=ft.Stack(
            [
                ft.Row(
                    [
                        scrollable_viewer,
                        page_strip_vertical,
                        vertical_toolbar,
                    ],
                    spacing=6,
                ),
                bookmarks_overlay,
                viewer_loading_overlay,
            ],
        ),
    )

    middle_resize_handle = _build_resize_handle(controller, "middle")

    # Rail shown when tab panel collapsed; entire strip clickable to re-expand
    tab_expand_rail = ft.Container(
        ref=refs["tab_expand_rail"],
        width=18,
        bgcolor="grey200",
        visible=controller.state.ui.tab_panel_collapsed,
        tooltip="Expand panel",
        content=ft.GestureDetector(
            on_tap=lambda _: controller.toggle_tab_panel(),
            content=ft.Container(
                expand=True,
                alignment=ft.alignment.center,
                content=ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16),
            ),
        ),
    )

    main_content = ft.Row(
        [
            middle_column,
            middle_resize_handle,
            tab_expand_rail,
            right_column,
        ],
        expand=True,
        spacing=0,
    )

    root = ft.Column(
        [
            main_content,
        ],
        expand=True,
    )
    return root
