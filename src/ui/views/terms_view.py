"""Terms tab view - Search term management"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from src.core.state.ui_state import refs

if TYPE_CHECKING:
    from src.controllers.main_controller import MainController


def build_view(controller: "MainController") -> ft.Container:
    """Build the Terms tab — search term management."""
    return ft.Container(
        bgcolor="grey100",
        padding=10,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.TextField(
                            ref=refs["new_term_input"],
                            hint_text="Add term",
                            expand=True,
                            on_submit=controller.search_term.add_term,
                        ),
                        ft.IconButton("add", on_click=controller.search_term.add_term),
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
        ),
    )
