"""Controller for bookmark/TOC panel and navigation"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from src.core.state.ui_state import refs
from src.ui.views import bookmarks_view

if TYPE_CHECKING:
    from src.controllers.main_controller import MainController


def _safe_update(control: ft.Control | None) -> bool:
    """Update control only if attached to page. Prevents errors during teardown."""
    if control is None:
        return False
    try:
        if getattr(control, "page", None) is not None:
            control.update()
            return True
    except Exception:
        pass
    return False


class BookmarkController:
    """Handles bookmark panel visibility, view switching, and TOC navigation."""

    def __init__(
        self,
        main_controller: MainController,
        page: ft.Page,
    ) -> None:
        self.main_controller = main_controller
        self.page = page

    def toggle_bookmarks_panel(self) -> None:
        """Toggle bookmarks overlay panel visibility."""
        current = self.main_controller.state.viewer.bookmarks_panel_visible
        self.main_controller.state.viewer.bookmarks_panel_visible = not current

        overlay = refs.get("bookmarks_overlay")
        if overlay and overlay.current:
            overlay.current.visible = not current
            _safe_update(overlay.current)

            if not current:
                bookmarks_view.render_bookmarks_list(
                    refs["bookmarks_list"].current.data
                    if refs["bookmarks_list"].current
                    else ""
                )
