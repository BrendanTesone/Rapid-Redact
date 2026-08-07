"""AI Detection tab view - LLM-powered CCI detection with base_results_view."""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Callable

import flet as ft

from src.core.state.ui_state import refs
from src.ui.views import base_results_view

if TYPE_CHECKING:
    from src.controllers.ai.ai_detection_controller import AIDetectionController
    from src.controllers.main_controller import MainController

logger = logging.getLogger(__name__)

_controller: AIDetectionController | None = None
_main_controller: MainController | None = None

refs["btn_pick_cci_library"] = ft.Ref[ft.ElevatedButton]()
refs["txt_cci_library_name"] = ft.Ref[ft.Text]()
refs["btn_test_auth"] = ft.Ref[ft.ElevatedButton]()
refs["btn_ai_scan_continuous"] = ft.Ref[ft.ElevatedButton]()
refs["btn_ai_scan_current_page"] = ft.Ref[ft.ElevatedButton]()
refs["btn_ai_scan_continuous"] = ft.Ref[ft.ElevatedButton]()
refs["ai_scan_progress_container"] = ft.Ref[ft.Container]()
refs["ai_scan_progress_bar"] = ft.Ref[ft.ProgressBar]()
refs["ai_scan_status"] = ft.Ref[ft.Text]()
refs["btn_cancel_ai_scan"] = ft.Ref[ft.ElevatedButton]()


def _build_success_overlay(
    creds_text: str, close_callback: Callable[[ft.ControlEvent | None], None]
) -> ft.Container:
    return ft.Container(
        bgcolor="white",
        padding=20,
        border_radius=8,
        width=500,
        shadow=ft.BoxShadow(
            spread_radius=1,
            blur_radius=10,
            color="black,0.25",
        ),
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            "AI Connection Successful",
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            color="green",
                        ),
                        ft.IconButton(
                            ft.Icons.CLOSE,
                            icon_size=16,
                            on_click=close_callback,
                            tooltip="Close",
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Text("✓ API credentials are valid and working.", size=13),
                ft.Divider(height=1),
                ft.Text("Authentication Details:", size=12, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=ft.Text(creds_text, size=11, font_family="Courier New"),
                    bgcolor="#f5f5f5",
                    padding=10,
                    border_radius=4,
                ),
            ],
            spacing=10,
            tight=True,
            scroll=ft.ScrollMode.AUTO,
        ),
    )


def _build_failure_overlay(
    error_msg: str,
    creds_text: str,
    close_callback: Callable[[ft.ControlEvent | None], None],
) -> ft.Container:
    return ft.Container(
        bgcolor="white",
        padding=20,
        border_radius=8,
        width=500,
        shadow=ft.BoxShadow(
            spread_radius=1,
            blur_radius=10,
            color="black,0.25",
        ),
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            "AI Connection Failed",
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            color="red",
                        ),
                        ft.IconButton(
                            ft.Icons.CLOSE,
                            icon_size=16,
                            on_click=close_callback,
                            tooltip="Close",
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Text(f"✗ {error_msg}", size=13),
                ft.Divider(height=1),
                ft.Text("Authentication Details:", size=12, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=ft.Text(creds_text, size=11, font_family="Courier New"),
                    bgcolor="#f5f5f5",
                    padding=10,
                    border_radius=4,
                ),
                ft.Divider(height=1),
                ft.Text("Troubleshooting:", size=12, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "1. Check .env file exists with correct credentials\n"
                    "2. Verify AI_API_KEY, AI_API_BASE_URL (optional), AI_API_MODEL are set\n"
                    "3. Check network connection\n"
                    "4. Verify API key is valid for your provider",
                    size=11,
                ),
            ],
            spacing=10,
            tight=True,
            scroll=ft.ScrollMode.AUTO,
        ),
    )


def register_controller(ctrl: AIDetectionController) -> None:
    global _controller
    _controller = ctrl


def register_main_controller(ctrl: MainController) -> None:
    global _main_controller
    _main_controller = ctrl
    base_results_view.register_controller(ctrl)


def _passes_ai_filters(result: object, filter_text: str) -> bool:
    show_dismissed_ref = refs.get("chk_ai_show_dismissed")
    if show_dismissed_ref and show_dismissed_ref.current:
        show_dismissed = show_dismissed_ref.current.value
        if not show_dismissed and result.dismissed:  # type: ignore[attr-defined]
            return False
    return True


def _navigate_to_ai_match(
    file_name: str, file_path: str, page: int, highlight: str
) -> None:
    """Navigate directly without setting current_term to show all highlights simultaneously."""
    if not _main_controller:
        return
    _main_controller.viewer.navigate_to_page(file_path, page)


def render_ai_detections_list() -> None:
    if not _main_controller:
        return

    from src.core.state.app_state import ResultCategory

    config = base_results_view.ResultsListConfig(
        listview_ref="ai_detections_list",
        term_predicate=lambda r: r.category == ResultCategory.AI,
        icon=ft.Icons.PSYCHOLOGY,
        icon_color="purple",
        dismiss_checkbox_ref="chk_ai_show_dismissed",
        passes_filters_fn=_passes_ai_filters,
        navigate_fn=_navigate_to_ai_match,
        toggle_fn=base_results_view.toggle_result_redaction_simple,
    )

    base_results_view.render_results_list(config, filter_text="")


def on_pick_library(e: ft.ControlEvent) -> None:
    if not e.page:
        return

    def on_result(result: ft.FilePickerResultEvent) -> None:
        if not result.files or not _controller:
            return

        library_path = result.files[0].path
        _controller.ai_state.library_path = library_path

        txt_name = refs["txt_cci_library_name"].current

        if txt_name:
            import os

            txt_name.value = os.path.basename(library_path)
            txt_name.italic = False
            txt_name.color = "black"

        if e.page:
            e.page.update()

    file_picker = ft.FilePicker(on_result=on_result)
    e.page.overlay.append(file_picker)
    e.page.update()

    file_picker.pick_files(
        dialog_title="Select CCI Library Excel File",
        allowed_extensions=["xlsx", "xls"],
        allow_multiple=False,
    )


def on_scan_clicked(e: ft.ControlEvent) -> None:
    if not _controller or not e.page:
        return

    if not _controller.state.project.file_list:
        e.page.snack_bar = ft.SnackBar(
            content=ft.Text("No PDF files loaded in project"), bgcolor="red"
        )
        e.page.snack_bar.open = True
        e.page.update()
        return

    btn_scan = refs["btn_ai_scan_continuous"].current
    btn_scan_current = refs["btn_ai_scan_current_page"].current
    progress_container = refs["ai_scan_progress_container"].current

    if btn_scan:
        btn_scan.disabled = True

    if btn_scan_current:
        btn_scan_current.disabled = True

    if progress_container:
        progress_container.visible = True

    e.page.update()

    _controller.run_ai_detection_scan()
    _start_progress_polling(e.page)


def on_scan_current_page_clicked(e: ft.ControlEvent) -> None:
    if not _controller or not _main_controller or not e.page:
        return

    current_file = _main_controller.state.viewer.file_path
    page_index = _main_controller.state.viewer.page_index
    current_page = page_index + 1

    logger.info(
        f"Scan current section clicked: file={current_file}, page_index={page_index}, current_page={current_page}"
    )

    if not current_file:
        e.page.snack_bar = ft.SnackBar(
            content=ft.Text("No PDF file currently open"), bgcolor="red"
        )
        e.page.snack_bar.open = True
        e.page.update()
        return

    btn_scan = refs["btn_ai_scan_continuous"].current
    btn_scan_current = refs["btn_ai_scan_current_page"].current
    progress_container = refs["ai_scan_progress_container"].current

    if btn_scan:
        btn_scan.disabled = True

    if btn_scan_current:
        btn_scan_current.disabled = True

    if progress_container:
        progress_container.visible = True

    e.page.update()

    _controller.run_ai_detection_current_page(current_file, current_page)
    _start_progress_polling(e.page)


def on_scan_continuous_clicked(e: ft.ControlEvent) -> None:
    """Process all bookmark sections sequentially starting from page 1."""
    if not _controller or not _main_controller or not e.page:
        return

    current_file = _main_controller.state.viewer.file_path

    if not current_file:
        e.page.snack_bar = ft.SnackBar(
            content=ft.Text("No PDF file currently open"), bgcolor="red"
        )
        e.page.snack_bar.open = True
        e.page.update()
        return

    btn_scan = refs["btn_ai_scan_continuous"].current
    btn_scan_current = refs["btn_ai_scan_current_page"].current
    btn_scan_continuous = refs["btn_ai_scan_continuous"].current
    progress_container = refs["ai_scan_progress_container"].current

    if btn_scan:
        btn_scan.disabled = True

    if btn_scan_current:
        btn_scan_current.disabled = True

    if btn_scan_continuous:
        btn_scan_continuous.disabled = True

    if progress_container:
        progress_container.visible = True

    e.page.update()

    _controller.run_ai_detection_continuous(current_file, 1, e.page, _main_controller)
    _start_progress_polling(e.page)


def _start_progress_polling(page: ft.Page) -> None:
    def poll_progress() -> None:
        while _controller and _controller.ai_state.scan_running:
            progress = _controller.ai_state.scan_progress
            status = _controller.ai_state.scan_status

            progress_bar = refs["ai_scan_progress_bar"].current
            status_text = refs["ai_scan_status"].current

            if progress_bar:
                progress_bar.value = progress

            if status_text:
                status_text.value = status

            page.update()
            time.sleep(0.5)

        _on_scan_complete(page)

    poll_thread = threading.Thread(target=poll_progress, daemon=True)
    poll_thread.start()


def _on_scan_complete(page: ft.Page) -> None:
    if not _controller or not _main_controller:
        return

    btn_scan = refs["btn_ai_scan_continuous"].current
    btn_scan_current = refs["btn_ai_scan_current_page"].current
    progress_container = refs["ai_scan_progress_container"].current

    if btn_scan:
        btn_scan.disabled = False

    if btn_scan_current:
        btn_scan_current.disabled = False

    if progress_container:
        progress_container.visible = False

    render_ai_detections_list()
    _main_controller.viewer._render_page_strip()

    from src.core.state.app_state import ResultCategory

    ai_results = [
        r
        for r in _main_controller.state.search.all_search_results
        if r.category == ResultCategory.AI and not r.dismissed
    ]

    current_file = _main_controller.state.viewer.file_path
    current_page = _main_controller.state.viewer.page_index + 1

    current_page_results = [
        r for r in ai_results if r.file_path == current_file and r.page == current_page
    ]

    if current_file:
        _main_controller.viewer.navigate_to_page(current_file, current_page)

    if ai_results:
        if current_page_results:
            page.snack_bar = ft.SnackBar(
                content=ft.Text(
                    f"✓ Scan complete: {len(ai_results)} total detection(s) found. "
                    f"{len(current_page_results)} on current page."
                ),
                bgcolor="green",
                duration=4000,
            )
        else:
            page.snack_bar = ft.SnackBar(
                content=ft.Text(
                    f"✓ Scan complete: {len(ai_results)} detection(s) found. "
                    f"None on current page."
                ),
                bgcolor="blue",
                duration=4000,
            )
    else:
        page.snack_bar = ft.SnackBar(
            content=ft.Text("Scan complete: No CCI detections found."),
            bgcolor="grey",
            duration=3000,
        )

    page.snack_bar.open = True
    page.update()


def on_cancel_scan(e: ft.ControlEvent) -> None:
    if not _controller:
        return
    _controller.cancel_scan()


def on_test_auth_clicked(e: ft.ControlEvent) -> None:
    if not _controller or not e.page:
        return

    overlay_ref = refs.get("auth_test_overlay")
    if not overlay_ref or not overlay_ref.current:
        logger.error("auth_test_overlay ref not found")
        return

    overlay = overlay_ref.current
    page = e.page

    overlay.content = ft.Container(
        bgcolor="white",
        padding=20,
        border_radius=8,
        shadow=ft.BoxShadow(spread_radius=1, blur_radius=10, color="black,0.25"),
        content=ft.Row(
            [
                ft.ProgressRing(width=24, height=24, stroke_width=3),
                ft.Text("Testing AI Connection...", size=13),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=12,
            tight=True,
        ),
    )
    overlay.visible = True
    overlay.update()

    def close_overlay(e_inner: ft.ControlEvent | None = None) -> None:
        overlay.visible = False
        overlay.content = None
        overlay.update()

    def test_auth_worker() -> None:
        success = False
        error_msg = ""
        auth_details: dict[str, str] = {}

        try:
            from src.controllers.ai.llm_client import LiteLLMClient

            client = _controller.llm_client
            if isinstance(client, LiteLLMClient):
                auth_details = {
                    "API Key": (
                        "***" + client.api_key[-4:]
                        if client.api_key
                        else "NOT SET"
                    ),
                    "Base URL": client.base_url if client.base_url else "(Direct provider)",
                    "Model": client.model,
                }
            else:
                auth_details = {
                    "API Key": "N/A",
                    "Base URL": "N/A",
                    "Model": "N/A",
                }

            success = _controller.llm_client.test_authentication()
            if not success:
                error_msg = "Authentication failed. Check API key and model name."
        except Exception as ex:
            logger.error(f"Auth test error: {ex}")
            error_msg = f"Auth test error: {str(ex)}"

        async def show_result() -> None:
            try:
                creds_text = "\n".join([f"{k}: {v}" for k, v in auth_details.items()])

                if success:
                    overlay.content = _build_success_overlay(creds_text, close_overlay)
                else:
                    overlay.content = _build_failure_overlay(
                        error_msg, creds_text, close_overlay
                    )
                overlay.update()
            except Exception as ex:
                logger.error(f"Error showing overlay: {ex}")
                close_overlay()

        page.run_task(show_result)

    auth_thread = threading.Thread(target=test_auth_worker, daemon=True)
    auth_thread.start()


def build_view(controller: AIDetectionController) -> ft.Container:
    register_controller(controller)

    auth_overlay = ft.Container(
        ref=refs["auth_test_overlay"],
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
                    ft.Text("Testing AI Connection...", size=13),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=12,
                tight=True,
            ),
        ),
    )

    main_content = ft.Column(
        [
            ft.Row(
                [
                    ft.ElevatedButton(
                        "Select CCI Library",
                        ref=refs["btn_pick_cci_library"],
                        icon=ft.Icons.FOLDER_OPEN,
                        on_click=lambda e: on_pick_library(e),
                    ),
                    ft.Text(
                        ref=refs["txt_cci_library_name"],
                        value="No file selected (optional)",
                        size=11,
                        color="grey",
                        italic=True,
                    ),
                ],
                spacing=10,
            ),
            ft.Divider(height=1, color="blue"),
            ft.ElevatedButton(
                "Test Authentication",
                ref=refs["btn_test_auth"],
                icon=ft.Icons.VERIFIED_USER,
                on_click=lambda e: on_test_auth_clicked(e),
                bgcolor="orange",
                color="white",
                width=float("inf"),
            ),
            ft.Divider(height=1),
            ft.Row(
                [
                    ft.ElevatedButton(
                        "SCAN ENTIRE DOCUMENT",
                        ref=refs["btn_ai_scan_continuous"],
                        on_click=lambda e: on_scan_continuous_clicked(e),
                        bgcolor="blue",
                        color="white",
                        expand=True,
                        disabled=False,
                    ),
                    ft.ElevatedButton(
                        "SCAN CURRENT SECTION",
                        ref=refs["btn_ai_scan_current_page"],
                        on_click=lambda e: on_scan_current_page_clicked(e),
                        bgcolor="green",
                        color="white",
                        expand=True,
                        disabled=False,
                    ),
                ],
                spacing=5,
            ),
            ft.Container(
                ref=refs["ai_scan_progress_container"],
                visible=False,
                content=ft.Column(
                    [
                        ft.ProgressBar(ref=refs["ai_scan_progress_bar"], value=0.0),
                        ft.Text(ref=refs["ai_scan_status"], value="", size=11),
                        ft.ElevatedButton(
                            "Cancel Scan",
                            ref=refs["btn_cancel_ai_scan"],
                            on_click=lambda e: on_cancel_scan(e),
                            bgcolor="orange",
                            color="white",
                        ),
                    ],
                    spacing=5,
                ),
            ),
            ft.Divider(height=1),
            ft.Checkbox(
                ref=refs["chk_ai_show_dismissed"],
                label="Show Dismissed",
                value=False,
                on_change=lambda e: render_ai_detections_list(),
            ),
            ft.ListView(
                ref=refs["ai_detections_list"], expand=True, spacing=0, padding=5
            ),
        ]
    )

    return ft.Container(
        padding=5,
        content=ft.Stack(
            [
                main_content,
                auth_overlay,
            ]
        ),
    )
