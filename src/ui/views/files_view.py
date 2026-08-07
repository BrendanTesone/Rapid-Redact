"""
Files tab view - PDF selection, project management, terms, and search
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Callable

import flet as ft

from src.core.state.ui_state import refs

if TYPE_CHECKING:
    from src.controllers.main_controller import MainController

_controller: MainController | None = None


def register_controller(ctrl: MainController) -> None:
    global _controller
    _controller = ctrl


def _safe_call(name: str, file_path: str) -> None:
    """Placeholder - callback registration handled by controller."""
    pass


def render_file_list() -> None:
    """Render the file list showing all loaded PDFs with their redaction status."""
    lv = refs.get("results_list")
    if lv:
        lv = lv.current
    if not lv:
        return

    lv.controls.clear()

    file_list = _controller.state.project.file_list if _controller else []

    if not file_list:
        lv.controls.append(ft.Text("No PDF files found.", color="grey"))
    else:
        pending_count = 0
        for file_path in file_list:
            fname = os.path.basename(file_path)
            has_reds = False
            if _controller:
                if fname in _controller.state.project.redactions:
                    has_reds = any(
                        boxes
                        for boxes in _controller.state.project.redactions[
                            fname
                        ].values()
                    )
                if not has_reds and fname in _controller.state.project.toc_redactions:
                    has_reds = bool(_controller.state.project.toc_redactions[fname])
            if has_reds:
                pending_count += 1

        header_text = f"FILES ({len(file_list)})"
        if pending_count > 0:
            header_text += f"  •  {pending_count} with redactions"

        lv.controls.append(ft.Text(header_text, weight="bold"))

        batch_status = (
            _controller.state.project.batch_save_status if _controller else {}
        )

        for file_path in file_list:
            fname = os.path.basename(file_path)

            has_redactions = False
            redaction_count = 0
            toc_count = 0
            if _controller:
                if fname in _controller.state.project.redactions:
                    has_redactions = any(
                        boxes
                        for boxes in _controller.state.project.redactions[
                            fname
                        ].values()
                    )
                if (
                    not has_redactions
                    and fname in _controller.state.project.toc_redactions
                ):
                    has_redactions = bool(
                        _controller.state.project.toc_redactions[fname]
                    )

                redaction_count = sum(
                    len(boxes)
                    for boxes in _controller.state.project.redactions.get(
                        fname, {}
                    ).values()
                )
                toc_count = len(_controller.state.project.toc_redactions.get(fname, {}))

            file_status = batch_status.get(fname, "")

            if file_status == "saved":
                icon = ft.Icon(ft.Icons.CHECK_CIRCLE, color="green", size=20)
                status_tooltip = "Saved successfully"
            elif file_status == "saving":
                icon = ft.Icon(ft.Icons.HOURGLASS_BOTTOM, color="blue", size=20)
                status_tooltip = "Saving..."
            elif file_status.startswith("error:"):
                icon = ft.Icon(ft.Icons.ERROR, color="red", size=20)
                status_tooltip = f"Save error: {file_status[6:]}"
            elif has_redactions:
                icon = ft.Icon(ft.Icons.PENDING_ACTIONS, color="orange", size=20)
                status_tooltip = "Has unsaved redactions"
            else:
                icon = ft.Icon(ft.Icons.PICTURE_AS_PDF, color="blue", size=20)
                status_tooltip = "No redactions"

            subtitle_parts = []
            if redaction_count > 0:
                subtitle_parts.append(
                    f"{redaction_count} redaction{'s' if redaction_count != 1 else ''}"
                )
            if toc_count > 0:
                subtitle_parts.append(
                    f"{toc_count} TOC edit{'s' if toc_count != 1 else ''}"
                )
            if file_status == "saved":
                subtitle_parts.append("✓ Saved")
            elif file_status == "saving":
                subtitle_parts.append("⏳ Saving...")
            elif file_status.startswith("error:"):
                subtitle_parts.append("✗ Error")

            subtitle_text = "  ·  ".join(subtitle_parts) if subtitle_parts else None

            trailing_control = None
            if _controller is not None:
                trailing_control = ft.IconButton(
                    ft.Icons.CLOSE,
                    icon_size=16,
                    icon_color="grey",
                    tooltip="Remove from list",
                    on_click=lambda _, p=file_path: _controller.project_persistence.remove_file_from_list(
                        p
                    ),
                )

            is_selected = False

            lv.controls.append(
                ft.ListTile(
                    leading=icon,
                    title=ft.Text(fname, weight="bold" if is_selected else None),
                    subtitle=(
                        ft.Text(subtitle_text, size=10, color="grey")
                        if subtitle_text
                        else None
                    ),
                    trailing=trailing_control,
                    selected=is_selected,
                    bgcolor="#E3F2FD" if is_selected else None,
                    on_click=lambda _, p=file_path: _safe_call("file_click", p),
                    tooltip=status_tooltip,
                )
            )

    if lv.page:
        lv.update()


def build_term_table_row(
    index: int,
    term: str,
    active: bool,
    on_toggle: Callable[[int, bool], None],
    on_delete: Callable[[int], None],
) -> ft.DataRow:
    """Build a single term table row with checkbox and delete button."""
    return ft.DataRow(
        cells=[
            ft.DataCell(
                ft.Checkbox(
                    value=active,
                    on_change=lambda ev: on_toggle(index, bool(ev.control.value)),
                )
            ),
            ft.DataCell(ft.Text(term)),
            ft.DataCell(
                ft.IconButton(
                    "delete",
                    icon_color="red",
                    on_click=lambda _: on_delete(index),
                )
            ),
        ]
    )


def build_import_dialog(
    imported_count: int,
    on_merge: Callable[[ft.ControlEvent], None],
    on_replace: Callable[[ft.ControlEvent], None],
    on_cancel: Callable[[ft.ControlEvent], None],
) -> ft.AlertDialog:
    """Build the import terms dialog with merge/replace/cancel options."""
    return ft.AlertDialog(
        modal=True,
        title=ft.Text("Import Terms"),
        content=ft.Text(
            f"Found {imported_count} terms in file.\nMerge with existing terms or replace all?"
        ),
        actions=[
            ft.TextButton("Merge", on_click=on_merge),
            ft.TextButton("Replace All", on_click=on_replace),
            ft.TextButton("Cancel", on_click=on_cancel),
        ],
    )


def build_view(controller: "MainController") -> ft.Container:
    """Build the Project Settings tab — project save/load and PDF export operations.

    Contains project persistence (save/load project state) and PDF export
    operations (PleaseReview, Adobe Redactions).
    """
    return ft.Container(
        bgcolor="grey100",
        padding=10,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Save Project",
                            icon="save",
                            bgcolor="#1565C0",
                            color="white",
                            tooltip="Save all redactions, terms, dismissed matches to a .json file",
                            on_click=controller.project_persistence.save_project,
                            expand=True,
                            style=ft.ButtonStyle(
                                padding=ft.padding.symmetric(horizontal=8, vertical=6),
                            ),
                        ),
                        ft.ElevatedButton(
                            "Load Project",
                            icon="folder_open",
                            bgcolor="#4527A0",
                            color="white",
                            tooltip="Load a previously saved project file",
                            on_click=controller.project_persistence.load_project,
                            expand=True,
                            style=ft.ButtonStyle(
                                padding=ft.padding.symmetric(horizontal=8, vertical=6),
                            ),
                        ),
                    ],
                    spacing=8,
                ),
                ft.Divider(),
                ft.ElevatedButton(
                    "Save Current PDF for PleaseReview",
                    icon=ft.Icons.SAVE_ALT,
                    bgcolor="#2196F3",
                    color="white",
                    tooltip="Save current PDF with yellow highlight comments for review",
                    on_click=controller.project_persistence.save_pdf_for_pleasereview,
                    width=float("inf"),
                    style=ft.ButtonStyle(
                        padding=ft.padding.symmetric(horizontal=8, vertical=6),
                    ),
                ),
                ft.ElevatedButton(
                    "Save Current PDF With Adobe Redactions",
                    icon=ft.Icons.SAVE,
                    bgcolor="#4CAF50",
                    color="white",
                    tooltip="Save current PDF with redactions applied (file picker)",
                    on_click=controller.project_persistence.save_pdf,
                    width=float("inf"),
                    style=ft.ButtonStyle(
                        padding=ft.padding.symmetric(horizontal=8, vertical=6),
                    ),
                ),
                ft.ElevatedButton(
                    "Save All PDFs with Adobe Redactions",
                    icon=ft.Icons.SAVE_ALT,
                    bgcolor="#FF9800",
                    color="white",
                    tooltip="Save all PDFs with redactions to a folder (folder picker)",
                    on_click=controller.export.batch_save_all_pdfs,
                    width=float("inf"),
                    style=ft.ButtonStyle(
                        padding=ft.padding.symmetric(horizontal=8, vertical=6),
                    ),
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
        ),
    )
