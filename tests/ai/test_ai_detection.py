"""Tests for AI detection coordinate lookup."""

import tempfile
from pathlib import Path

import fitz

from src.core.domain.ai_detection import (
    _exact_search,
    _extract_target_coords,
    _find_subsequence,
    _fuzzy_search,
    find_text_coordinates,
)
from src.core.state.app_state import PdfBox


def create_test_pdf(text_content: str) -> str:
    """Create a temporary PDF with given text."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text_content)

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_name = tmp.name
    tmp.close()  # Close file handle before fitz saves
    doc.save(tmp_name)
    doc.close()
    return tmp_name


def test_exact_search_single_match() -> None:
    """Test exact search with single match."""
    pdf_path = create_test_pdf("This is a test document with unique text.")

    try:
        matches = _exact_search(pdf_path, "unique text", 1)

        assert len(matches) == 1
        assert isinstance(matches[0], PdfBox)
        assert matches[0].w > 0
        assert matches[0].h > 0
    finally:
        Path(pdf_path).unlink()


def test_exact_search_multiple_matches() -> None:
    """Test exact search with multiple matches."""
    pdf_path = create_test_pdf("test word appears twice: test")

    try:
        matches = _exact_search(pdf_path, "test", 1)

        assert len(matches) == 2
    finally:
        Path(pdf_path).unlink()


def test_exact_search_no_match() -> None:
    """Test exact search with no match."""
    pdf_path = create_test_pdf("This is a test document.")

    try:
        matches = _exact_search(pdf_path, "nonexistent", 1)

        assert len(matches) == 0
    finally:
        Path(pdf_path).unlink()


def test_find_coordinates_unique_match() -> None:
    """Test coordinate lookup with unique match."""
    pdf_path = create_test_pdf("Patient received ABC-123 protocol.")

    try:
        coords = find_text_coordinates(
            pdf_path=pdf_path,
            target_text="ABC-123",
            page_hint=1,
            context="Patient received ABC-123 protocol",
        )

        assert len(coords) == 1
        assert coords[0].w > 0
    finally:
        Path(pdf_path).unlink()


def test_find_subsequence() -> None:
    """Test subsequence finding helper."""
    words = ["patient", "received", "test", "protocol"]
    target = ["test"]

    idx = _find_subsequence(words, target)
    assert idx == 2

    target_multi = ["received", "test"]
    idx = _find_subsequence(words, target_multi)
    assert idx == 1


def test_extract_target_coords() -> None:
    """Test extracting target coords from expanded match."""
    expanded_box = PdfBox(x=100.0, y=50.0, w=200.0, h=20.0)
    target = "test"
    expanded_text = "patient received test protocol"

    # Should return approximate coordinates for "test" within expanded box
    result = _extract_target_coords(expanded_box, target, expanded_text)

    assert result is not None
    assert result.x >= expanded_box.x
    assert result.y == expanded_box.y
    assert result.w <= expanded_box.w
    assert result.h == expanded_box.h


def test_fuzzy_search_with_typo() -> None:
    """Test fuzzy search finds text with minor differences."""
    pdf_path = create_test_pdf("Patient received ABC-123 protocol.")

    try:
        # Search for slightly different text (OCR variation)
        result = _fuzzy_search(pdf_path, "ABC-l23", 1, threshold=0.8)

        # Should find "ABC-123" as similar match
        assert result is not None
        assert result.w > 0
    finally:
        Path(pdf_path).unlink()


def test_fuzzy_search_no_match_below_threshold() -> None:
    """Test fuzzy search returns None when similarity too low."""
    pdf_path = create_test_pdf("Patient received ABC-123 protocol.")

    try:
        result = _fuzzy_search(pdf_path, "completely different", 1, threshold=0.8)

        assert result is None
    finally:
        Path(pdf_path).unlink()
