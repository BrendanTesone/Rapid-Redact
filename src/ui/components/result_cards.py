"""Reusable UI components for result cards.

This module provides building blocks for rendering search results,
dose results, and consistency gaps with consistent styling.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import flet as ft


@dataclass(frozen=True)
class HighlightedText:
    """Text with highlighting information."""

    full_text: str
    highlight: str


def build_highlighted_spans(text: HighlightedText) -> list[ft.TextSpan]:
    """Build Flet TextSpan list with yellow highlighting for matched text.

    Performs case-insensitive matching but preserves original casing in displayed text.
    """
    if not text.highlight:
        return [ft.TextSpan(text.full_text)]

    lower_text = text.full_text.lower()
    lower_highlight = text.highlight.lower()

    if lower_highlight not in lower_text:
        return [ft.TextSpan(text.full_text)]

    spans: list[ft.TextSpan] = []
    current_pos = 0
    highlight_len = len(text.highlight)

    while True:
        start_pos = lower_text.find(lower_highlight, current_pos)
        if start_pos == -1:
            if current_pos < len(text.full_text):
                spans.append(ft.TextSpan(text.full_text[current_pos:]))
            break

        if start_pos > current_pos:
            spans.append(ft.TextSpan(text.full_text[current_pos:start_pos]))

        end_pos = start_pos + highlight_len
        spans.append(
            ft.TextSpan(
                text.full_text[start_pos:end_pos],
                style=ft.TextStyle(bgcolor="yellow", weight="bold"),
            )
        )

        current_pos = end_pos

    return spans


@dataclass(frozen=True)
class Badge:
    """UI badge configuration."""

    text: str
    bgcolor: str
    text_color: str = "white"
    tooltip: str = ""
    size: int = 9


def build_badge(badge: Badge) -> ft.Container:
    """Build a small colored badge container."""
    return ft.Container(
        content=ft.Text(
            badge.text, size=badge.size, color=badge.text_color, weight="bold"
        ),
        bgcolor=badge.bgcolor,
        border_radius=8,
        padding=ft.padding.symmetric(horizontal=6, vertical=1),
        tooltip=badge.tooltip or None,
    )


@dataclass(frozen=True)
class ActionButton:
    """Action button configuration."""

    label: str
    bgcolor: str
    on_click: Callable[[ft.ControlEvent], None]
    tooltip: str = ""
    size: int = 10
    text_color: str = "white"


def build_action_button(button: ActionButton) -> ft.Container:
    """Build a small action button."""
    return ft.Container(
        content=ft.Text(button.label, size=button.size, color=button.text_color),
        bgcolor=button.bgcolor,
        padding=5,
        border_radius=3,
        on_click=button.on_click,
        tooltip=button.tooltip or None,
    )
