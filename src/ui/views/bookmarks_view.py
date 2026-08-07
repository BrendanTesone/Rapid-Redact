"""
Bookmarks tab view - PDF bookmark navigation
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Protocol

import flet as ft

from src.core.domain.pdf_search import (
    find_term_with_wildcard,
    preprocess_text,
    get_matches_in_page_range,
)
from src.core.state.app_state import AppState, BookmarkItem, RedactionBox
from src.core.state.ui_state import refs

if TYPE_CHECKING:
    from src.controllers.main_controller import MainController
    from src.controllers.viewer_controller import ViewerController
    from src.controllers.redaction.data_controller import RedactionDataController
    from src.controllers.redaction.rendering_controller import (
        RedactionRenderingController,
    )
else:

    class ViewerController(Protocol):
        """Protocol for viewer controller methods."""

        def navigate_to_page(
            self, file_path: str, page_num: int, highlight_term: str = ""
        ) -> None: ...

        def render_viewer(self, initial: bool = False) -> None: ...

    class RedactionDataController(Protocol):
        """Protocol for redaction data controller methods."""

        def add_redaction_internal(
            self, pdf_box: RedactionBox, page_idx: int, file_name: str | None = None
        ) -> None: ...

        def remove_batch_redaction(self, fname: str, batch_id: str) -> None: ...

    class RedactionRenderingController(Protocol):
        """Protocol for redaction rendering controller methods."""

        def render_viewer(self) -> None: ...

    class MainController(Protocol):
        """Protocol for main controller to avoid circular import."""

        state: AppState
        page: object
        viewer: ViewerController
        redaction_data: RedactionDataController
        redaction_rendering: RedactionRenderingController


_controller: MainController | None = None


def register_controller(ctrl: MainController) -> None:
    global _controller
    _controller = ctrl


def build_view(controller: MainController) -> ft.Container:
    return ft.Container(
        padding=5,
        content=ft.Column(
            [
                ft.TextField(
                    hint_text="Filter...",
                    height=35,
                    on_change=lambda e: render_bookmarks_list(e.control.value),
                ),
                ft.ListView(
                    ref=refs["bookmarks_list"], expand=True, spacing=5, item_extent=50
                ),
            ],
            spacing=6,
        ),
    )


def render_bookmarks_list(filter_text: str = "") -> None:
    lv = refs["bookmarks_list"].current
    if not lv or _controller is None:
        return

    lv.data = filter_text
    lv.controls.clear()

    display_items = _controller.state.project.current_file_bookmarks

    if not display_items:
        lv.controls.append(
            ft.Text(
                "No bookmarks loaded. Select a file to view its bookmarks.",
                italic=True,
            )
        )
        if lv.page:
            lv.update()
        return

    def find_match_in_terms(title: str) -> str | None:
        assert _controller is not None
        title_str = str(title)
        title_lower = title_str.lower()

        if filter_text and filter_text.lower() in title_lower:
            return filter_text

        for t in _controller.state.search.active_search_terms:
            if "*" in t:
                matches_iter = find_term_with_wildcard(t, preprocess_text(title_str))
                first_match = next(iter(matches_iter), None)
                if first_match is not None:
                    return t
            else:
                if t.lower() in title_lower:
                    return t
        return None

    for i, it in enumerate(display_items):
        it.original_index = i

        fname = _controller.state.viewer.file_name
        title = it.title
        if (
            fname
            and fname in _controller.state.project.toc_redactions
            and i in _controller.state.project.toc_redactions[fname]
        ):
            title = _controller.state.project.toc_redactions[fname][i]

        match_term = find_match_in_terms(title)
        spans: list[ft.TextSpan] = [ft.TextSpan(title)]

        if match_term:
            if "*" in match_term:
                matches_iter = find_term_with_wildcard(
                    match_term, preprocess_text(title)
                )
                m = next(iter(matches_iter), None)
                if m:
                    start, end = m.span()
                    spans = [
                        ft.TextSpan(title[:start]),
                        ft.TextSpan(
                            title[start:end],
                            style=ft.TextStyle(bgcolor="yellow", weight="bold"),
                        ),
                        ft.TextSpan(title[end:]),
                    ]
            else:
                m = re.search(re.escape(match_term), title, flags=re.IGNORECASE)
                if m:
                    start, end = m.span()
                    spans = [
                        ft.TextSpan(title[:start]),
                        ft.TextSpan(
                            title[start:end],
                            style=ft.TextStyle(bgcolor="yellow", weight="bold"),
                        ),
                        ft.TextSpan(title[end:]),
                    ]

        page_num = it.page
        term_to_redact = match_term or it.term or ""

        is_title_redacted = it.title_redacted
        is_toc_term_redacted = it.redacted_term_toc
        is_pages_term_redacted = it.redacted_term_pages

        btn_title_text = "Un-Redact Title" if is_title_redacted else "Redact Title"
        btn_title_col = "green" if is_title_redacted else "orange"

        term_btn_row = ft.Row([], spacing=6)
        if term_to_redact:
            toc_btn_text = (
                "Un-Redact TOC"
                if is_toc_term_redacted
                else f"Redact TOC '{term_to_redact}'"
            )
            toc_btn_col = "green" if is_toc_term_redacted else "orange"

            pages_btn_text = (
                "Un-Redact Pages"
                if is_pages_term_redacted
                else f"Redact Pages '{term_to_redact}'"
            )
            pages_btn_col = "green" if is_pages_term_redacted else "red"

            term_btn_row.controls.append(
                ft.Container(
                    content=ft.Text(
                        toc_btn_text,
                        size=9,
                        color="black" if not is_toc_term_redacted else "white",
                    ),
                    bgcolor=toc_btn_col,
                    padding=3,
                    border_radius=3,
                    on_click=lambda e, i=it, t=term_to_redact: toggle_bookmark_term_toc_redaction(
                        i, t
                    ),
                )
            )
            term_btn_row.controls.append(
                ft.Container(
                    content=ft.Text(pages_btn_text, size=9, color="white"),
                    bgcolor=pages_btn_col,
                    padding=3,
                    border_radius=3,
                    on_click=lambda e, i=it, t=term_to_redact: toggle_bookmark_term_pages_redaction(
                        i, t
                    ),
                )
            )

        lv.controls.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.BOOKMARK,
                                    size=14,
                                    color="blue",
                                ),
                                ft.Container(
                                    content=ft.Text(
                                        spans=spans,
                                        size=13,
                                        weight="bold",
                                        no_wrap=False,
                                    ),
                                    expand=True,
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                        ft.Row(
                            [
                                ft.Text(
                                    f"Pp {it.page} - {it.end_page}",
                                    size=10,
                                    color="grey",
                                ),
                                ft.Row(
                                    [
                                        term_btn_row,
                                        ft.Container(
                                            content=ft.Text(
                                                btn_title_text,
                                                size=9,
                                                color="white",
                                            ),
                                            bgcolor=btn_title_col,
                                            padding=3,
                                            border_radius=3,
                                            on_click=lambda e, i=it: toggle_bookmark_title_redaction(
                                                i
                                            ),
                                        ),
                                    ],
                                    spacing=6,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ]
                ),
                padding=ft.padding.only(
                    left=(it.level - 1) * 15 + 5,
                    top=5,
                    bottom=5,
                    right=5,
                ),
                border=ft.border.only(bottom=ft.border.BorderSide(1, "grey100")),
                on_click=lambda _, f=it.file_path or _controller.state.viewer.file_path, p=page_num: (
                    _controller.viewer.navigate_to_page(f, p)
                    if _controller and f
                    else None
                ),
            )
        )

    if lv.page:
        lv.update()


def toggle_bookmark_term_toc_redaction(item: BookmarkItem, term: str) -> None:
    if not _controller or not _controller.state.viewer.file_name or item.original_index is None:
        return

    fname = _controller.state.viewer.file_name
    toc_index = item.original_index

    is_redacted = item.redacted_term_toc

    if is_redacted:
        if (
            fname in _controller.state.project.toc_redactions
            and toc_index in _controller.state.project.toc_redactions[fname]
        ):
            del _controller.state.project.toc_redactions[fname][toc_index]
        item.redacted_term_toc = False
    else:
        _controller.state.project.toc_redactions.setdefault(fname, {})
        original_title = item.title
        term_literal = term.replace("*", "")
        redacted_title = (
            re.sub(
                re.escape(term_literal),
                "█████",
                original_title,
                flags=re.IGNORECASE,
            )
            if term_literal
            else original_title
        )
        _controller.state.project.toc_redactions[fname][toc_index] = redacted_title
        item.redacted_term_toc = True

    lv_ref = refs["bookmarks_list"].current
    if lv_ref:
        render_bookmarks_list(str(lv_ref.data) if lv_ref.data else "")


def toggle_bookmark_term_pages_redaction(item: BookmarkItem, term: str) -> None:
    if not _controller:
        return

    fname = _controller.state.viewer.file_name
    fpath = item.file_path or _controller.state.viewer.file_path
    if not fname or not fpath:
        return

    is_redacted = item.redacted_term_pages

    start_p = item.page - 1
    end_p = item.end_page - 1
    end_p = min(end_p, _controller.state.viewer.total_pages - 1)

    if is_redacted:
        batch_id = item.term_pages_batch_id
        if batch_id:
            _controller.redaction_data.remove_batch_redaction(fname, batch_id)
        item.redacted_term_pages = False
        item.term_pages_batch_id = None
    else:
        term_literal = term.replace("*", "")
        matches = get_matches_in_page_range(fpath, term_literal, start_p, end_p)
        if matches:
            batch_id = str(uuid.uuid4())
            for m in matches:
                box = RedactionBox(
                    id=str(uuid.uuid4()),
                    x=float(m["x"]),
                    y=float(m["y"]),
                    w=float(m["w"]),
                    h=float(m["h"]),
                    page=int(m["page"]),
                    batch_id=batch_id,
                )
                _controller.redaction_data.add_redaction_internal(
                    box, int(m["page"]), fname
                )
            item.redacted_term_pages = True
            item.term_pages_batch_id = batch_id

    lv_ref = refs["bookmarks_list"].current
    if lv_ref:
        render_bookmarks_list(str(lv_ref.data) if lv_ref.data else "")
    if _controller and (file_path := _controller.state.viewer.file_path):
        _controller.viewer.navigate_to_page(
            file_path, _controller.state.viewer.page_index + 1
        )


def toggle_bookmark_title_redaction(item: BookmarkItem) -> None:
    """Renames title to 'CCI' when redacted."""
    if not _controller or not _controller.state.viewer.file_name or item.original_index is None:
        return

    fname = _controller.state.viewer.file_name
    toc_index = item.original_index

    if item.title_redacted:
        if (
            fname in _controller.state.project.toc_redactions
            and toc_index in _controller.state.project.toc_redactions[fname]
        ):
            del _controller.state.project.toc_redactions[fname][toc_index]
        item.title_redacted = False
    else:
        _controller.state.project.toc_redactions.setdefault(fname, {})
        _controller.state.project.toc_redactions[fname][toc_index] = "CCI"
        item.title_redacted = True

    lv_ref = refs["bookmarks_list"].current
    if lv_ref:
        render_bookmarks_list(str(lv_ref.data) if lv_ref.data else "")
