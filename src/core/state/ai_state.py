"""AI detection state dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from src.core.state.app_state import PdfBox


class CCILibraryItem(TypedDict):
    """An item in the CCI library."""

    redacted_text: str
    context: str
    category: str
    justification: str


@dataclass(slots=True)
class AIDetection:
    """A single AI-detected CCI item."""

    text: str
    page: int
    file_name: str
    file_path: str
    confidence: str
    category: str
    justification: str
    context: str
    rects: list[PdfBox]
    redacted: bool = False
    dismissed: bool = False
    batch_id: str = ""


@dataclass(slots=True)
class AIDetectionState:
    """State for AI-powered CCI detection."""

    library_path: str | None = None
    scan_running: bool = False
    scan_progress: float = 0.0
    scan_status: str = ""
    all_detections: list[AIDetection] = field(default_factory=list)
    cancel_requested: bool = False
    document_summaries: dict[str, dict[str, str]] = field(default_factory=dict)
