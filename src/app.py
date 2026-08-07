from __future__ import annotations

import io
import sys

import flet as ft
import fitz

from src.config import AppConfig
from src.controllers.main_controller import MainController
from src.ui.views import ai_detection_view

# Suppress MuPDF warnings for PDFs with malformed structure trees
try:
    fitz.TOOLS.mupdf_display_errors(False)
except AttributeError:
    sys.stderr = io.StringIO()


def main(page: ft.Page) -> None:
    config = AppConfig.from_env()

    page.title = "Rapid Redact Prerelease"
    page.theme_mode = "light"
    page.padding = 0
    page.window.maximized = True
    page.window.min_width = config.ui.window_min_width
    page.window.min_height = config.ui.window_min_height

    controller = MainController(page, config)

    page.on_keyboard_event = controller.on_keyboard

    ai_detection_view.register_controller(controller.ai_detection)
    ai_detection_view.register_main_controller(controller)

    controller.project_persistence.register_pickers()

    page.add(controller.create_view())

    # Initialize term table after UI is added to page (refs must be set first)
    controller.search_term.refresh_term_table()
