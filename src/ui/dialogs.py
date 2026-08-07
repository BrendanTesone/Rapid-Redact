"""Dialog helpers for repeat-redaction workflow and keyboard shortcuts."""

from __future__ import annotations

import copy
import uuid
from typing import Protocol

import flet as ft

from src.core.domain.pdf_rendering import get_pdf_page_data
from src.core.state.app_state import RedactionBox, AppState


class _ControllerProtocol(Protocol):
    page: ft.Page
    state: AppState

    @property
    def redaction_data(self) -> "_RedactionDataProtocol": ...

    @property
    def viewer(self) -> "_ViewerProtocol": ...


class _RedactionDataProtocol(Protocol):
    def add_redaction_internal(
        self, box: RedactionBox, page_idx: int, file_name: str
    ) -> None: ...


class _ViewerProtocol(Protocol):
    def navigate_to_page(self, file_path: str, page_num: int) -> None: ...


def open_dialog(page: ft.Page, dialog: ft.AlertDialog) -> None:
    """Open AlertDialog with fallback for older Flet versions."""
    if hasattr(page, "open"):
        page.open(dialog)
        return

    page.dialog = dialog
    dialog.open = True
    page.update()


def close_dialog(page: ft.Page, dialog: ft.AlertDialog) -> None:
    """Close AlertDialog with fallback for older Flet versions."""
    if hasattr(page, "close"):
        page.close(dialog)
        return

    dialog.open = False
    page.update()


def parse_pages_spec(spec: str, total_pages: int) -> list[int]:
    """
    Parse a print-style page spec into a sorted list of unique 0-based page indices.

    Examples:
        "1-3,7" -> [0, 1, 2, 6]
        "5" -> [4]
        " 1 - 3 , 7 " -> [0, 1, 2, 6]

    Rules:
    - Input is 1-based; output is 0-based indices.
    - Ranges are inclusive and must be ascending.
    - Pages must be within 1..total_pages.

    Raises:
        ValueError for invalid syntax or out-of-range values.
    """
    if total_pages <= 0:
        raise ValueError("Total pages must be known and > 0.")

    cleaned = (spec or "").strip()
    if not cleaned:
        raise ValueError("Please enter pages (e.g. 1-6,9,29,31-34).")

    indices: set[int] = set()
    segments = [s.strip() for s in cleaned.split(",") if s.strip()]
    if not segments:
        raise ValueError("Please enter pages (e.g. 1-6,9,29,31-34).")

    for seg in segments:
        if "-" in seg:
            left, right = [p.strip() for p in seg.split("-", maxsplit=1)]
            if not left or not right:
                raise ValueError(f"Invalid range '{seg}'. Use like '3-7'.")
            if not (left.isdigit() and right.isdigit()):
                raise ValueError(f"Range must be numeric: '{seg}'.")
            start = int(left)
            end = int(right)
            if start < 1 or end < 1:
                raise ValueError(f"Pages must be >= 1: '{seg}'.")
            if start > end:
                raise ValueError(f"Range must be ascending: '{seg}'.")
            if end > total_pages:
                raise ValueError(f"Range '{seg}' exceeds total pages ({total_pages}).")
            for p in range(start, end + 1):
                indices.add(p - 1)
        else:
            if not seg.isdigit():
                raise ValueError(f"Invalid page '{seg}'. Use numbers and ranges only.")
            p = int(seg)
            if p < 1:
                raise ValueError(f"Pages must be >= 1: '{seg}'.")
            if p > total_pages:
                raise ValueError(f"Page '{p}' exceeds total pages ({total_pages}).")
            indices.add(p - 1)

    out = sorted(indices)
    if not out:
        raise ValueError("No valid pages found.")
    return out


def _ensure_total_pages(
    controller: _ControllerProtocol,
    file_path: str,
    page_index: int,
    zoom: float,
    base_width: int,
) -> int:
    total_pages = controller.state.viewer.total_pages
    if total_pages > 0:
        return total_pages

    _, _, _, _, total_pages = get_pdf_page_data(file_path, page_index, zoom, base_width)
    controller.state.viewer.total_pages = total_pages
    if total_pages <= 0:
        raise RuntimeError("Unable to determine total pages for this PDF.")
    return total_pages


def remove_repeat_draft_box(
    controller: _ControllerProtocol, draft_box: RedactionBox
) -> None:
    fname = controller.state.viewer.file_name
    pidx = controller.state.viewer.page_index
    if not fname or pidx is None:
        return
    if (
        fname not in controller.state.project.redactions
        or pidx not in controller.state.project.redactions[fname]
    ):
        return

    controller.state.project.redactions[fname][pidx] = [
        b
        for b in controller.state.project.redactions[fname][pidx]
        if b.id != draft_box.id
    ]


def apply_repeat_to_page_indices(
    controller: _ControllerProtocol, draft_box: RedactionBox, page_indices: list[int]
) -> int:
    """
    Commit repeat draft and clone to selected pages.

    Semantics: Only apply to selected pages. If current page not selected,
    remove draft from current page. If selected, commit draft in place.

    Returns number of pages applied to.
    """
    file_path = controller.state.viewer.file_path
    if not file_path:
        raise RuntimeError("No PDF is loaded.")

    total_pages = _ensure_total_pages(
        controller=controller,
        file_path=file_path,
        page_index=controller.state.viewer.page_index,
        zoom=controller.state.viewer.zoom,
        base_width=controller.state.viewer.base_width,
    )

    wanted = sorted(set(page_indices))
    if not wanted:
        raise ValueError("No pages specified.")
    for idx in wanted:
        if idx < 0 or idx >= total_pages:
            raise ValueError(f"Invalid page index {idx}; must be 0..{total_pages - 1}.")

    fname = controller.state.viewer.file_name
    if not fname:
        raise RuntimeError("No file_name in state.")

    current_idx = controller.state.viewer.page_index
    batch_id = str(uuid.uuid4())

    if current_idx in wanted:
        draft_box.is_repeat_draft = False
        draft_box.batch_id = batch_id
    else:
        remove_repeat_draft_box(controller, draft_box)

    applied = 0
    for idx in wanted:
        if idx == current_idx:
            applied += 1
            continue

        clone = copy.deepcopy(draft_box)
        clone.id = str(uuid.uuid4())
        clone.batch_id = batch_id
        controller.redaction_data.add_redaction_internal(clone, idx, fname)
        applied += 1

    return applied


def show_repeat_dialog(
    controller: _ControllerProtocol, draft_box: RedactionBox
) -> None:
    """
    Show dialog to choose repeat scope (all pages or print-style syntax "1-6,9,29,31-34").
    OK applies immediately. Cancel removes the draft box. Dialog stays open on validation errors.
    """
    page: ft.Page = controller.page
    file_path = controller.state.viewer.file_path
    if not file_path:
        raise RuntimeError("No PDF is loaded.")

    total_pages = _ensure_total_pages(
        controller=controller,
        file_path=file_path,
        page_index=controller.state.viewer.page_index,
        zoom=controller.state.viewer.zoom,
        base_width=controller.state.viewer.base_width,
    )

    error_text = ft.Text(value="", color="red", size=11)

    pages_field = ft.TextField(
        label="Pages",
        width=320,
        hint_text="e.g. 1-6,9,29,31-34",
        value=str(controller.state.viewer.page_index + 1),
        disabled=True,
    )

    def on_choice_change(val: str) -> None:
        pages_field.disabled = val != "pages"
        pages_field.update()

    choice_group = ft.RadioGroup(
        value="all",
        content=ft.Column(
            [
                ft.Radio(value="all", label="All pages"),
                ft.Radio(value="pages", label="Pages (print-style)"),
            ],
            spacing=6,
            tight=True,
        ),
        on_change=lambda e: on_choice_change(e.control.value),
    )

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Repeat redaction scope"),
        content=ft.Column(
            [
                ft.Text(f"Total pages: {total_pages}", size=12),
                choice_group,
                pages_field,
                error_text,
            ],
            tight=True,
            spacing=10,
        ),
        actions_alignment=ft.MainAxisAlignment.END,
    )

    def on_cancel(_: ft.ControlEvent) -> None:
        remove_repeat_draft_box(controller, draft_box)
        close_dialog(page, dialog)
        if file_path := controller.state.viewer.file_path:
            controller.viewer.navigate_to_page(
                file_path, controller.state.viewer.page_index + 1
            )

    def on_ok(_: ft.ControlEvent) -> None:
        error_text.value = ""
        error_text.update()
        try:
            mode = choice_group.value
            if mode == "all":
                selected = list(range(0, total_pages))
            elif mode == "pages":
                selected = parse_pages_spec(pages_field.value, total_pages)
            else:
                raise ValueError(f"Unsupported selection: {mode}")

            applied = apply_repeat_to_page_indices(controller, draft_box, selected)
            page.open(
                ft.SnackBar(
                    ft.Text(f"Repeat applied to {applied} page(s)."), bgcolor="blue"
                )
            )
            if file_path := controller.state.viewer.file_path:
                controller.viewer.navigate_to_page(
                    file_path, controller.state.viewer.page_index + 1
                )
            close_dialog(page, dialog)
        except Exception as ex:
            error_text.value = str(ex)
            error_text.update()

    dialog.actions = [
        ft.TextButton("Cancel", on_click=on_cancel),
        ft.FilledButton("OK", on_click=on_ok),
    ]

    open_dialog(page, dialog)


def create_shortcuts_dialog(page: ft.Page) -> ft.AlertDialog:
    shortcuts = [
        ("Ctrl+Z", "Undo"),
        ("Ctrl+Y", "Redo"),
        ("Ctrl+A", "Select all on page"),
        ("Delete", "Delete selected annotations"),
        ("← / Page Up", "Previous page"),
        ("→ / Page Down", "Next page"),
        ("Home", "First page"),
        ("End", "Last page"),
    ]

    rows: list[ft.Row] = []
    for keys, desc in shortcuts:
        rows.append(
            ft.Row(
                [
                    ft.Container(
                        content=ft.Text(keys, size=12, weight="bold", color="blue"),
                        width=180,
                    ),
                    ft.Text(desc, size=12),
                ],
                spacing=10,
            )
        )

    dlg: ft.AlertDialog = ft.AlertDialog(
        title=ft.Text("Keyboard Shortcuts"),
        content=ft.Column(
            rows,
            scroll=ft.ScrollMode.AUTO,
            height=min(len(rows) * 30, 500),
        ),
    )
    dlg.actions = [ft.TextButton("Close", on_click=lambda e: page.close(dlg))]

    return dlg
