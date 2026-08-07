"""Pure rendering layer for text selection: converts selection state into visual overlays."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import flet as ft

if TYPE_CHECKING:
    from src.core.state.selection_state import SelectionSpan, TextSelection


class PageStackProtocol(Protocol):
    controls: list[ft.Control]

    def update(self) -> None: ...


class SelectionRenderer:
    """Stateless renderer for text selection highlights."""

    HIGHLIGHT_COLOR = "#80FFC107"
    PREVIEW_MARKER = "text_selection_preview"
    ANCHOR_COLOR = "#FF2196F3"
    FOCUS_COLOR = "#FFFF5722"
    SNAP_EDGE_COLOR = "#FF4CAF50"
    DEBUG_POINT_SIZE = 8.0

    def render(
        self,
        selection: TextSelection,
        page_stack: PageStackProtocol,
        scale: float,
    ) -> list[ft.Control]:
        if not selection.range or selection.range.is_empty:
            return []

        overlays: list[ft.Control] = []
        for span in selection.range.spans:
            overlay = self._create_highlight_rectangle(span, scale)
            overlays.append(overlay)

        return overlays

    def _create_highlight_rectangle(
        self, span: SelectionSpan, scale: float
    ) -> ft.Container:
        left = float(span.x0 * scale)
        top = float(span.y0 * scale)
        width = float((span.x1 - span.x0) * scale)
        height = float((span.y1 - span.y0) * scale)

        return ft.Container(
            left=left,
            top=top,
            width=width,
            height=height,
            bgcolor=self.HIGHLIGHT_COLOR,
            data=self.PREVIEW_MARKER,
            border_radius=2,
        )

    def clear(self, page_stack: PageStackProtocol) -> None:
        page_stack.controls = [
            c
            for c in page_stack.controls
            if getattr(c, "data", None) != self.PREVIEW_MARKER
        ]

    def update_rendering(
        self,
        selection: TextSelection,
        page_stack: PageStackProtocol,
        scale: float,
    ) -> None:
        self.clear(page_stack)

        if selection.is_active and not selection.is_collapsed:
            overlays = self.render(selection, page_stack, scale)
            page_stack.controls.extend(overlays)

        if selection.is_active:
            if selection.start:
                page_stack.controls.append(
                    self._create_debug_point(
                        selection.start.x, selection.start.y, self.ANCHOR_COLOR, scale
                    )
                )
            if selection.focus:
                page_stack.controls.append(
                    self._create_debug_point(
                        selection.focus.x, selection.focus.y, self.FOCUS_COLOR, scale
                    )
                )

        if selection.is_active and selection.range and not selection.range.is_empty:
            snap_edge = self._compute_snap_edge_point(selection)
            if snap_edge is not None:
                page_stack.controls.append(
                    self._create_debug_point(
                        snap_edge[0], snap_edge[1], self.SNAP_EDGE_COLOR, scale
                    )
                )

        try:
            page_stack.update()
        except Exception:
            pass

    def _create_debug_point(
        self, pdf_x: float, pdf_y: float, color: str, scale: float
    ) -> ft.Container:
        half = self.DEBUG_POINT_SIZE / 2
        return ft.Container(
            left=float(pdf_x * scale) - half,
            top=float(pdf_y * scale) - half,
            width=self.DEBUG_POINT_SIZE,
            height=self.DEBUG_POINT_SIZE,
            bgcolor=color,
            border_radius=self.DEBUG_POINT_SIZE / 2,
            data=self.PREVIEW_MARKER,
        )

    def _compute_snap_edge_point(
        self, selection: "TextSelection"
    ) -> tuple[float, float] | None:
        if not selection.range or not selection.range.spans:
            return None
        if selection.start is None or selection.focus is None:
            return None

        spans = selection.range.spans
        start, focus = selection.start, selection.focus

        forward = focus.y > start.y or (
            abs(focus.y - start.y) < 5 and focus.x >= start.x
        )

        if forward:
            last = spans[-1]
            return (last.x1, (last.y0 + last.y1) / 2)
        else:
            first = spans[0]
            return (first.x0, (first.y0 + first.y1) / 2)
