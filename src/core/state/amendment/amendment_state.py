"""Amendment transfer state - manages redaction extraction from redline PDFs."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.state.app_state import RedactionBox


@dataclass(slots=True)
class AmendmentState:
    """State for amendment redaction transfer feature."""

    redline_pdf_path: str | None = None
    redline_pdf_name: str | None = None
    extracted_redactions: dict[int, list[RedactionBox]] = field(default_factory=dict)
    total_pages: int = 0
    redline_page_count: int = 0
    page_offset: int = 0
    extraction_status: str = "idle"
    extraction_error: str | None = None
    transfer_status: str = "idle"
    transfer_stats: dict[str, int] = field(default_factory=dict)
    transfer_error: str | None = None
