"""PDF text position mapping utilities.

Maps PDF coordinate rectangles to character offsets in processed text.
This enables extracting unique context for each instance of duplicate words.
"""

from __future__ import annotations

import fitz


def find_text_offset_for_rect(
    page: fitz.Page,
    rect: fitz.Rect,
    processed_text: str,
    overlap_threshold: float = 0.5,
) -> tuple[int, int] | None:
    """Map PDF rectangle coordinates to character offsets in processed text.

    Args:
        page: PyMuPDF page object
        rect: Target rectangle with PDF coordinates
        processed_text: Normalized page text (whitespace collapsed to single spaces)
        overlap_threshold: Minimum word coverage ratio (0.0-1.0) to consider overlap

    Returns:
        (start_offset, end_offset) tuple for match in processed_text,
        or None if mapping fails
    """
    words = page.get_text("words") or []
    if not words:
        return None

    sorted_words = sorted(words, key=lambda w: (int(w[5]), int(w[6]), int(w[7])))

    overlapping_words: list[tuple[float, float, float, float, str, int, int, int]] = []
    for w in sorted_words:
        word_rect = fitz.Rect(w[0], w[1], w[2], w[3])
        word_area = word_rect.width * word_rect.height

        if word_area <= 0:
            continue

        intersection = word_rect & rect
        if intersection.is_empty:
            continue

        intersection_area = intersection.width * intersection.height
        coverage = intersection_area / word_area
        if coverage >= overlap_threshold:
            overlapping_words.append(w)

    if not overlapping_words:
        return None

    current_offset = 0
    match_start_offset: int | None = None
    match_text_parts: list[str] = []

    for i, w in enumerate(sorted_words):
        word_text = str(w[4])

        if w in overlapping_words:
            if match_start_offset is None:
                match_start_offset = current_offset
            match_text_parts.append(word_text)

        current_offset += len(word_text)
        if i < len(sorted_words) - 1:
            current_offset += 1

    if match_start_offset is None:
        return None

    match_length = sum(len(part) for part in match_text_parts)
    if len(match_text_parts) > 1:
        match_length += len(match_text_parts) - 1
    match_end_offset = match_start_offset + match_length

    # Validate against processed_text with search window
    # Offset might be slightly off due to whitespace normalization differences
    match_text = " ".join(str(w[4]) for w in overlapping_words)
    search_window_start = max(0, match_start_offset - 10)
    search_window_end = min(len(processed_text), match_end_offset + 10)
    search_window = processed_text[search_window_start:search_window_end]

    window_offset = search_window.lower().find(match_text.lower())
    if window_offset >= 0:
        final_start = search_window_start + window_offset
        final_end = final_start + len(match_text)
        return (final_start, final_end)

    # Fallback to calculated offsets if validation fails
    return (match_start_offset, match_end_offset)


def extract_context_for_rect(
    page: fitz.Page,
    rect: fitz.Rect,
    processed_text: str,
    context_size: int = 50,
) -> str:
    """Extract context string for a specific PDF rectangle.

    Combines coordinate-to-offset mapping with sentence context extraction
    to provide unique context for each instance of duplicate text.

    Args:
        page: PyMuPDF page object
        rect: Target rectangle with PDF coordinates
        processed_text: Normalized page text
        context_size: Minimum context characters to extract around match

    Returns:
        Context string with surrounding text for this specific instance
    """
    from src.core.domain.pdf_search import extract_sentence_context

    offsets = find_text_offset_for_rect(page, rect, processed_text)
    if offsets is None:
        if len(processed_text) > 100:
            return processed_text[:100] + "..."
        return processed_text

    start_offset, end_offset = offsets

    return extract_sentence_context(
        processed_text, start_offset, end_offset, min_context=context_size
    )
