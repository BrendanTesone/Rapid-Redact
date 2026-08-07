"""
Persistent redaction data that survives across sessions.

This module defines type aliases for redaction storage structures.
"""

from __future__ import annotations

from typing import TypeAlias

from src.core.state.app_state import RedactionBox

ProjectRedactions: TypeAlias = dict[str, dict[int, list[RedactionBox]]]
ProjectTOCRedactions: TypeAlias = dict[str, dict[int, str]]
