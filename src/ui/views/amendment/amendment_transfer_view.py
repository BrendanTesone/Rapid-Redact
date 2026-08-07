"""Amendment Redaction Transfer tab view - transfer redactions between amendments."""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from src.core.state.ui_state import refs
from src.core.state.app_state import RedactionBox

if TYPE_CHECKING:
    from src.controllers.main_controller import MainController

refs["amendment_transfer_container"] = ft.Ref[ft.Container]()
refs["amendment_status_text"] = ft.Ref[ft.Text]()
refs["amendment_redline_name"] = ft.Ref[ft.Text]()
refs["amendment_redactions_list"] = ft.Ref[ft.Column]()
refs["amendment_send_all_button"] = ft.Ref[ft.ElevatedButton]()
refs["amendment_extract_all_button"] = ft.Ref[ft.ElevatedButton]()
refs["amendment_progress_bar"] = ft.Ref[ft.ProgressBar]()
refs["amendment_progress_text"] = ft.Ref[ft.Text]()
refs["amendment_progress_ring"] = ft.Ref[ft.ProgressRing]()
refs["amendment_debug_page_field"] = ft.Ref[ft.TextField]()


def build_view(controller: MainController) -> ft.Container:
    amendment_state = controller.state.amendment

    status_text = "No redline PDF loaded"
    redline_name = ""

    if amendment_state.redline_pdf_path:
        redline_name = amendment_state.redline_pdf_name or ""
        total_redactions = sum(
            len(boxes) for boxes in amendment_state.extracted_redactions.values()
        )
        status_text = f"Loaded: {total_redactions} redactions from {amendment_state.total_pages} pages"

    return ft.Container(
        ref=refs["amendment_transfer_container"],
        padding=20,
        content=ft.Column(
            [
                ft.Text(
                    "Amendment Redaction Transfer",
                    size=20,
                    weight="bold",
                ),
                ft.Divider(height=1),
                ft.Container(height=10),
                ft.Container(
                    content=ft.Row(
                        [
                            ft.ProgressRing(
                                ref=refs["amendment_progress_ring"],
                                width=20,
                                height=20,
                                visible=False,
                            ),
                            ft.Column(
                                [
                                    ft.ProgressBar(
                                        ref=refs["amendment_progress_bar"],
                                        value=0,
                                        visible=False,
                                        width=400,
                                    ),
                                    ft.Text(
                                        "",
                                        ref=refs["amendment_progress_text"],
                                        size=11,
                                        color="grey700",
                                        visible=False,
                                    ),
                                ],
                                spacing=5,
                                expand=True,
                            ),
                        ],
                        spacing=10,
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    height=60,
                ),
                ft.ElevatedButton(
                    "Load Redline PDF",
                    icon=ft.Icons.UPLOAD_FILE,
                    on_click=lambda _: controller.amendment.pick_redline_pdf(),
                    width=250,
                ),
                ft.Container(height=5),
                ft.Text(
                    redline_name,
                    ref=refs["amendment_redline_name"],
                    size=11,
                    color="blue",
                    italic=True,
                ),
                ft.Container(height=10),
                ft.ElevatedButton(
                    "Open Destination File",
                    icon=ft.Icons.FOLDER_OPEN,
                    on_click=lambda _: controller.amendment.pick_destination_pdf(),
                    width=250,
                ),
                ft.Container(height=10),
                ft.ElevatedButton(
                    "Send All to Document",
                    icon=ft.Icons.SEND_AND_ARCHIVE,
                    on_click=lambda _: controller.amendment.transfer_redactions_to_viewer(),
                    ref=refs["amendment_send_all_button"],
                    width=250,
                ),
                ft.Container(height=5),
                ft.Text(
                    status_text,
                    ref=refs["amendment_status_text"],
                    size=12,
                    color="grey700",
                ),
                ft.Container(height=30),
                ft.Container(
                    content=ft.Text(
                        "DEBUG OPERATIONS",
                        size=16,
                        weight="bold",
                        color=ft.Colors.ORANGE_900,
                    ),
                    bgcolor=ft.Colors.ORANGE_50,
                    padding=10,
                    border=ft.border.all(2, ft.Colors.ORANGE_200),
                    border_radius=5,
                ),
                ft.Container(height=10),
                ft.ElevatedButton(
                    "Extract and Interpret All Pages",
                    icon=ft.Icons.ANALYTICS,
                    on_click=lambda _: controller.amendment.extract_and_interpret_all(),
                    disabled=not amendment_state.redline_pdf_path,
                    ref=refs["amendment_extract_all_button"],
                    width=250,
                ),
                ft.Container(height=15),
                ft.Text(
                    "Single Page Operations",
                    size=12,
                    weight="bold",
                    color="grey700",
                ),
                ft.Container(height=5),
                ft.TextField(
                    ref=refs["amendment_debug_page_field"],
                    label="Page(s)",
                    hint_text="1 or 1-5,7,10-12",
                    width=200,
                    value="1",
                    keyboard_type=ft.KeyboardType.TEXT,
                ),
                ft.ElevatedButton(
                    "Extract Page(s)",
                    icon=ft.Icons.DOWNLOAD,
                    on_click=lambda _: controller.amendment.extract_current_page(),
                    tooltip="Extract raw redaction boxes from specified page(s)",
                ),
                ft.ElevatedButton(
                    "Extract and Interpret Page(s)",
                    icon=ft.Icons.GRID_ON,
                    on_click=lambda _: controller.amendment.extract_and_interpret_current_page(),
                    tooltip="Extract and interpret redactions from specified page(s)",
                ),
                ft.ElevatedButton(
                    "Extract, Interpret & Transfer Page(s)",
                    icon=ft.Icons.SEND,
                    on_click=lambda _: controller.amendment.extract_interpret_transfer_page(),
                    tooltip="Extract, interpret, and transfer redactions from specified page(s) to viewer",
                ),
                ft.Container(height=20),
                ft.Divider(height=1),
                ft.Text("Individual Redactions", size=13, weight="bold"),
                ft.Container(height=5),
                ft.Column(
                    ref=refs["amendment_redactions_list"],
                    controls=_build_redactions_list(controller),
                    spacing=5,
                    scroll=ft.ScrollMode.AUTO,
                ),
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        ),
    )


def _build_redactions_list(controller: MainController) -> list[ft.Control]:
    amendment_state = controller.state.amendment

    if not amendment_state.extracted_redactions:
        return [
            ft.Text(
                "No redactions extracted yet", size=11, color="grey700", italic=True
            )
        ]

    controls = [
        ft.Container(height=5),
    ]

    for page_idx in sorted(amendment_state.extracted_redactions.keys()):
        redactions = amendment_state.extracted_redactions[page_idx]
        for redaction in redactions:
            if redaction.term == "TABLE":
                type_label = "TABLE"
                type_color = "orange"
                text_preview = "[Table]"
            elif redaction.term == "DRAWING_CLUSTER":
                type_label = "DRAWING"
                type_color = "blue"
                text_preview = "[Drawing cluster]"
            else:
                type_label = "TEXT"
                type_color = "green"
                text_preview = redaction.match or "[No text]"

            controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(
                                content=ft.Text(
                                    type_label,
                                    size=10,
                                    color="white",
                                    weight="bold",
                                ),
                                bgcolor=type_color,
                                padding=ft.padding.symmetric(horizontal=6, vertical=2),
                                border_radius=4,
                            ),
                            ft.Text(
                                f"Page {page_idx + 1}:",
                                size=11,
                                weight="bold",
                                width=70,
                            ),
                            ft.Text(
                                f'"{text_preview}"',
                                size=11,
                                color="grey800",
                                expand=True,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.SEND,
                                icon_size=16,
                                tooltip="Send to Document",
                                on_click=lambda _, p=page_idx, r=redaction: controller.amendment.transfer_single_redaction(
                                    p, r
                                ),
                            ),
                        ],
                        spacing=5,
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    padding=5,
                    border=ft.border.all(1, "grey300"),
                    border_radius=5,
                )
            )

    return controls


def _extract_redaction_text(
    pdf_path: str | None, page_idx: int, redaction: RedactionBox
) -> str:
    if not pdf_path:
        return "[No text]"

    from src.core.domain.pdf_rendering import extract_text_under_rect
    from src.core.state.app_state import PdfBox

    box = PdfBox(x=redaction.x, y=redaction.y, w=redaction.w, h=redaction.h)
    text = extract_text_under_rect(pdf_path, page_idx, box)

    if not text or len(text) < 1:
        return "[Empty box]"

    if len(text) > 100:
        return text[:100] + "..."
    return text


def update_progress(current: int, total: int, message: str) -> None:
    progress_bar_ref = refs.get("amendment_progress_bar")
    progress_text_ref = refs.get("amendment_progress_text")
    progress_ring_ref = refs.get("amendment_progress_ring")

    if progress_bar_ref and progress_bar_ref.current:
        if total > 0:
            progress_bar_ref.current.value = current / total
        else:
            progress_bar_ref.current.value = 0
        progress_bar_ref.current.visible = True
        progress_bar_ref.current.update()

    if progress_text_ref and progress_text_ref.current:
        progress_text_ref.current.value = message
        progress_text_ref.current.visible = True
        progress_text_ref.current.update()

    if progress_ring_ref and progress_ring_ref.current:
        progress_ring_ref.current.visible = True
        progress_ring_ref.current.update()


def hide_progress() -> None:
    progress_bar_ref = refs.get("amendment_progress_bar")
    progress_text_ref = refs.get("amendment_progress_text")
    progress_ring_ref = refs.get("amendment_progress_ring")

    if progress_bar_ref and progress_bar_ref.current:
        progress_bar_ref.current.visible = False
        progress_bar_ref.current.update()

    if progress_text_ref and progress_text_ref.current:
        progress_text_ref.current.visible = False
        progress_text_ref.current.update()

    if progress_ring_ref and progress_ring_ref.current:
        progress_ring_ref.current.visible = False
        progress_ring_ref.current.update()


def refresh_view(controller: MainController) -> None:
    amendment_state = controller.state.amendment

    status_ref = refs.get("amendment_status_text")
    if status_ref and status_ref.current:
        if amendment_state.redline_pdf_path:
            total_redactions = sum(
                len(boxes) for boxes in amendment_state.extracted_redactions.values()
            )
            if total_redactions > 0:
                status_ref.current.value = f"Loaded: {total_redactions} redactions from {amendment_state.total_pages} pages"
            else:
                status_ref.current.value = f"PDF loaded: {amendment_state.total_pages} pages (click 'Load All Redactions' to extract)"
        else:
            status_ref.current.value = "No redline PDF loaded"
        status_ref.current.update()

    name_ref = refs.get("amendment_redline_name")
    if name_ref and name_ref.current:
        name_ref.current.value = amendment_state.redline_pdf_name or ""
        name_ref.current.update()

    list_ref = refs.get("amendment_redactions_list")
    if list_ref and list_ref.current:
        list_ref.current.controls = _build_redactions_list(controller)
        list_ref.current.update()

    extract_all_button_ref = refs.get("amendment_extract_all_button")
    if extract_all_button_ref and extract_all_button_ref.current:
        extract_all_button_ref.current.disabled = not bool(
            amendment_state.redline_pdf_path
        )
        extract_all_button_ref.current.update()

    send_all_button_ref = refs.get("amendment_send_all_button")
    if send_all_button_ref and send_all_button_ref.current:
        send_all_button_ref.current.disabled = not bool(
            amendment_state.extracted_redactions
        )
        send_all_button_ref.current.update()
