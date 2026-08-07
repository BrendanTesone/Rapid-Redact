"""CCI library Excel parsing."""

import logging
from pathlib import Path

import openpyxl

from src.core.state.ai_state import CCILibraryItem

logger = logging.getLogger(__name__)


class CCILibraryError(Exception):
    """Error loading or parsing CCI library."""

    pass


def load_cci_library(file_path: str) -> list[CCILibraryItem]:
    """
    Load CCI library from Excel file.

    Expected columns: Document, Study ID, Page, Bookmark, Type, Redacted Text, Context, Date
    Used columns: Redacted Text, Context, Type

    Args:
        file_path: Path to Excel file (empty string returns empty library)

    Raises:
        CCILibraryError: If file not found or missing required columns
    """
    if not file_path:
        logger.info("No CCI library path provided - running without library examples")
        return []

    if not Path(file_path).exists():
        raise CCILibraryError(f"File not found: {file_path}")

    try:
        wb = openpyxl.load_workbook(file_path, read_only=True)
        ws = wb.active
        assert ws is not None, "Workbook has no active sheet"
    except Exception as e:
        raise CCILibraryError(f"Failed to open Excel file: {e}") from e

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise CCILibraryError("Excel file is empty")

    raw_headers = [str(h).strip() if h else "" for h in rows[0]]

    logger.info(f"Excel columns found: {', '.join(raw_headers)}")

    library: list[CCILibraryItem] = []
    for row in rows[1:]:
        if not row or all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        row_data: dict[str, str] = {}
        for idx, (header, cell) in enumerate(zip(raw_headers, row)):
            if header and cell is not None and str(cell).strip():
                row_data[header] = str(cell).strip()

        if not row_data:
            continue

        redacted_text = ""
        for key in row_data:
            key_lower = key.lower()
            if any(
                term in key_lower
                for term in ["redact", "text", "cci", "content", "snippet"]
            ):
                redacted_text = row_data[key]
                break

        if not redacted_text:
            for val in row_data.values():
                if len(val) > 10:
                    redacted_text = val
                    break

        context = ""
        for key in row_data:
            if "context" in key.lower():
                context = row_data[key]
                break

        category = ""
        for key in row_data:
            key_lower = key.lower()
            if any(term in key_lower for term in ["type", "category", "bookmark"]):
                category = row_data[key]
                break

        library.append(
            CCILibraryItem(
                redacted_text=redacted_text,
                context=context,
                category=category,
                justification="",
            )
        )

    logger.info(f"Loaded {len(library)} entries from CCI library")
    return library
