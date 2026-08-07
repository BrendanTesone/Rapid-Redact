"""Centralized application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class UIConfig:
    window_min_width: int = 1200
    window_min_height: int = 700
    resize_throttle_ms: float = 50.0
    panel_left_min_width: int = 200
    panel_left_max_width: int = 600
    panel_middle_min_width: int = 300
    panel_middle_max_width: int = 800
    panel_left_default_width: int = 320
    panel_middle_default_width: int = 460
    viewer_base_width: int = 800
    viewer_scroll_spacing: int = 12
    viewer_page_buffer: int = 3
    fallback_page_height: float = 1035.5


@dataclass(slots=True, frozen=True)
class SearchConfig:
    context_radius: int = 300
    min_context: int = 80
    max_term_length: int = 1000
    regex_timeout_ms: int = 5000
    dosing_context_window_words: int = 8


@dataclass(slots=True, frozen=True)
class AIAPIConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = "claude-opus-4.6"


@dataclass(slots=True, frozen=True)
class AppConfig:
    ui: UIConfig
    search: SearchConfig
    ai_api: AIAPIConfig

    @classmethod
    def from_env(cls) -> AppConfig:
        import sys
        from pathlib import Path

        from dotenv import load_dotenv

        # PyInstaller bundles .env in temporary extraction directory (_MEIPASS)
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            env_path = Path(sys._MEIPASS) / ".env"
        else:
            env_path = Path(__file__).parent.parent / ".env"

        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
        else:
            load_dotenv()

        def get_int(key: str, default: int) -> int:
            val = os.environ.get(key)
            return int(val) if val else default

        def get_float(key: str, default: float) -> float:
            val = os.environ.get(key)
            return float(val) if val else default

        ui = UIConfig(
            window_min_width=get_int("UI_MIN_WIDTH", 1200),
            window_min_height=get_int("UI_MIN_HEIGHT", 700),
            resize_throttle_ms=get_float("UI_RESIZE_THROTTLE_MS", 50.0),
            panel_left_min_width=get_int("UI_PANEL_LEFT_MIN", 200),
            panel_left_max_width=get_int("UI_PANEL_LEFT_MAX", 600),
            panel_middle_min_width=get_int("UI_PANEL_MIDDLE_MIN", 300),
            panel_middle_max_width=get_int("UI_PANEL_MIDDLE_MAX", 800),
            panel_left_default_width=get_int("UI_PANEL_LEFT_DEFAULT", 320),
            panel_middle_default_width=get_int("UI_PANEL_MIDDLE_DEFAULT", 414),
            viewer_base_width=get_int("UI_VIEWER_BASE_WIDTH", 800),
            viewer_scroll_spacing=get_int("UI_VIEWER_SCROLL_SPACING", 12),
            viewer_page_buffer=get_int("UI_VIEWER_PAGE_BUFFER", 3),
            fallback_page_height=get_float("UI_FALLBACK_PAGE_HEIGHT", 1035.5),
        )

        search = SearchConfig(
            context_radius=get_int("SEARCH_CONTEXT_RADIUS", 300),
            min_context=get_int("SEARCH_MIN_CONTEXT", 80),
            max_term_length=get_int("SEARCH_MAX_TERM_LENGTH", 1000),
            regex_timeout_ms=get_int("SEARCH_REGEX_TIMEOUT_MS", 5000),
            dosing_context_window_words=get_int("SEARCH_DOSING_CONTEXT_WORDS", 8),
        )

        ai_api = AIAPIConfig(
            base_url=os.environ.get("AI_API_BASE_URL", ""),
            api_key=os.environ.get("AI_API_KEY", ""),
            model=os.environ.get("AI_API_MODEL", "claude-opus-4.6"),
        )

        return cls(ui=ui, search=search, ai_api=ai_api)
