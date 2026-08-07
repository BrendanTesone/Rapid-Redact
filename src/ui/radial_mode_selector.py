"""
radial_mode_selector.py - Radial mode selector control

Replaces dropdown navigation with an expanding radial menu.
Occupies minimal space when collapsed, expands on hover.
"""

from __future__ import annotations

import math
from typing import Callable

import flet as ft


def create_radial_selector(
    modes: list[tuple[str, str]],
    on_mode_change: Callable[[str], None],
    initial_mode: str | None = None,
) -> ft.Container:
    """Create a radial mode selector.

    Args:
        modes: List of (mode_key, label) tuples. Example: [("viewer", "Viewer"), ("files", "Project")]
        on_mode_change: Callback when mode changes, receives mode_key as string
        initial_mode: Initial active mode key (defaults to first mode)

    Returns:
        Container with radial selector that expands on hover
    """
    if not modes:
        raise ValueError("Must provide at least one mode")

    state = {
        "active_mode": initial_mode or modes[0][0],
        "expanded": False,
    }

    center_btn_size = 65
    peripheral_btn_size = 50

    # Calculate radius to prevent button overlap in semicircle layout
    # For semicircle: chord distance d = 2r * sin(π/(2*(n-1))), need d >= peripheral_btn_size
    num_modes = len(modes)
    if num_modes > 1:
        min_radius = peripheral_btn_size / (
            2 * math.sin(math.pi / (2 * (num_modes - 1)))
        )
    else:
        min_radius = peripheral_btn_size
    radius = min_radius * 1.2

    stack_size = int(2 * radius + peripheral_btn_size + 40)
    center_x = stack_size / 2
    stack_size / 2

    collapsed_height = 80
    expanded_height = int(
        10 + center_btn_size / 2 + radius + peripheral_btn_size / 2 + 5
    )

    def handle_center_hover(e: ft.HoverEvent) -> None:
        if e.data == "true":
            state["expanded"] = True
            for btn in peripheral_btns.values():
                btn.opacity = 1
                btn.update()
            radial_stack.height = expanded_height
            menu.height = expanded_height
            radial_stack.update()
            menu.update()

    center_btn_top = 10
    center_btn_y = center_btn_top + center_btn_size / 2

    active_label = next(
        (label for key, label in modes if key == state["active_mode"]), modes[0][1]
    )
    center_btn = ft.Container(
        width=center_btn_size,
        height=center_btn_size,
        border_radius=center_btn_size / 2,
        bgcolor="blue",
        left=center_x - center_btn_size / 2,
        top=center_btn_top,  # Near top instead of center
        content=ft.Text(
            active_label,
            size=12,
            color="white",
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        ),
        alignment=ft.alignment.center,
        animate_position=200,
        animate_opacity=200,
        animate_scale=200,
        shadow=ft.BoxShadow(
            spread_radius=1,
            blur_radius=5,
            color="black,0.3",
        ),
        on_hover=handle_center_hover,
    )

    peripheral_btns: dict[str, ft.Container] = {}

    def select_mode(mode_key: str) -> None:
        if mode_key == state["active_mode"]:
            return

        state["active_mode"] = mode_key

        new_label = next((label for key, label in modes if key == mode_key), "")
        center_btn.content = ft.Text(
            new_label,
            size=12,
            color="white",
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        )
        center_btn.update()

        state["expanded"] = False
        for btn in peripheral_btns.values():
            btn.opacity = 0
        radial_stack.height = collapsed_height
        menu.height = collapsed_height
        radial_stack.update()
        menu.update()

        on_mode_change(mode_key)

    for i, (mode_key, label) in enumerate(modes):
        # Semicircle arrangement below center button: 180° (left) to 0° (right)
        angle = i * math.pi / (num_modes - 1)

        x = center_x + radius * math.cos(angle) - peripheral_btn_size / 2
        y = center_btn_y + radius * math.sin(angle) - peripheral_btn_size / 2

        peripheral_btn = ft.Container(
            width=peripheral_btn_size,
            height=peripheral_btn_size,
            border_radius=peripheral_btn_size / 2,
            bgcolor="white",
            border=ft.border.all(2, "blue200"),
            left=x,
            top=y,
            opacity=0,
            content=ft.Text(
                label,
                size=10,
                color="blue",
                weight=ft.FontWeight.W_500,
                text_align=ft.TextAlign.CENTER,
            ),
            alignment=ft.alignment.center,
            animate_position=200,
            animate_opacity=200,
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=3,
                color="black,0.2",
            ),
            on_click=lambda e, m=mode_key: select_mode(m),
        )
        peripheral_btns[mode_key] = peripheral_btn

    stack_controls = [center_btn] + list(peripheral_btns.values())
    radial_stack = ft.Stack(
        width=stack_size,
        height=collapsed_height,
        controls=stack_controls,
    )

    def handle_container_hover(e: ft.HoverEvent) -> None:
        if e.data == "false":
            state["expanded"] = False
            for btn in peripheral_btns.values():
                btn.opacity = 0
            radial_stack.height = collapsed_height
            menu.height = collapsed_height
            radial_stack.update()
            menu.update()

    menu = ft.Container(
        content=radial_stack,
        on_hover=handle_container_hover,
        height=collapsed_height,
        width=stack_size,
        alignment=ft.alignment.top_center,
        clip_behavior=ft.ClipBehavior.NONE,
        expand=False,
    )

    return menu


def main(page: ft.Page) -> None:
    page.title = "Radial Mode Selector Demo"
    page.padding = 50

    status = ft.Text("Selected: viewer", size=20)

    def on_mode_change(mode_key: str) -> None:
        status.value = f"Selected: {mode_key}"
        status.update()

    modes = [
        ("viewer", "Viewer"),
        ("files", "Project"),
        ("matches", "Matches"),
        ("ai_detect", "AI"),
        ("dose", "Dose"),
        ("gap", "Gap"),
    ]

    selector = create_radial_selector(modes, on_mode_change, initial_mode="viewer")

    page.add(
        ft.Column(
            [
                status,
                ft.Container(height=20),
                selector,
            ]
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
