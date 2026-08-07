"""
Viewer tab view - Shows all loaded PDFs with load buttons
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import flet as ft

from src.core.state.ui_state import refs

if TYPE_CHECKING:
    from src.controllers.main_controller import MainController

_controller: MainController | None = None


def set_controller(ctrl: MainController) -> None:
    global _controller
    _controller = ctrl


def render_viewer_list(filter_text: str = "") -> None:
    lv_ref: ft.Ref[ft.ListView] | None = refs.get("viewer_list")
    lv: ft.ListView | None = lv_ref.current if lv_ref else None
    if not lv:
        return

    lv.data = filter_text
    lv.controls.clear()

    file_list: list[str] = _controller.state.project.file_list if _controller else []

    if not file_list:
        lv.controls.append(ft.Text("No PDF files loaded.", color="grey"))
        if lv.page:
            lv.update()
        return

    filtered_files: list[str] = file_list
    if filter_text:
        ft_lower: str = filter_text.lower()
        filtered_files = [
            f for f in file_list if ft_lower in os.path.basename(f).lower()
        ]

    if not filtered_files:
        lv.controls.append(
            ft.Text("No files match the filter.", italic=True, color="grey")
        )
        if lv.page:
            lv.update()
        return

    for file_path in filtered_files:
        fname: str = os.path.basename(file_path)

        is_current: bool = (
            (_controller.state.viewer.file_path == file_path) if _controller else False
        )
        icon_name: str = ft.Icons.VISIBILITY if is_current else ft.Icons.PICTURE_AS_PDF

        remove_btn: ft.IconButton | None = None
        if _controller is not None:
            remove_btn = ft.IconButton(
                ft.Icons.CLOSE,
                icon_size=18,
                icon_color="red",
                tooltip="Remove from list",
                on_click=lambda _, p=file_path: _controller.project_persistence.remove_file_from_list(
                    p
                ),
            )

        lv.controls.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(
                            icon_name, size=24, color="green" if is_current else "blue"
                        ),
                        ft.Text(
                            fname,
                            weight="bold" if is_current else "normal",
                            size=13,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            expand=True,
                        ),
                        remove_btn,
                    ],
                    spacing=8,
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=10,
                bgcolor="#E8F5E9" if is_current else "white",
                border=ft.border.all(2, "#4CAF50" if is_current else "grey300"),
                border_radius=8,
                on_click=(
                    (lambda _, p=file_path: _controller.viewer.navigate_to_page(p, 1))
                    if _controller
                    else None
                ),
                ink=True,
            )
        )

    if lv.page:
        lv.update()


def build_view(controller: MainController) -> ft.Container:
    def on_load_pdfs(_: ft.ControlEvent) -> None:
        if controller._folder_picker:
            controller._folder_picker.pick_files(
                allowed_extensions=["pdf"],
                allow_multiple=True,
            )

    return ft.Container(
        padding=10,
        content=ft.Column(
            [
                ft.ElevatedButton(
                    "Load PDFs",
                    icon="upload_file",
                    bgcolor="#1565C0",
                    color="white",
                    width=float("inf"),
                    on_click=on_load_pdfs,
                    tooltip="Select PDF files to load into the project",
                ),
                ft.ListView(
                    ref=refs["viewer_list"],
                    expand=True,
                    spacing=8,
                    item_extent=65,
                ),
            ],
            spacing=10,
        ),
    )
