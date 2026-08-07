"""AI-powered CCI detection coordinate lookup."""

import logging
from difflib import SequenceMatcher

import fitz

from src.core.state.app_state import PdfBox

logger = logging.getLogger(__name__)


def _exact_search(pdf_path: str, text: str, page: int) -> list[PdfBox]:
    """Search for exact text match using PyMuPDF."""
    doc = fitz.open(pdf_path)

    if page < 1 or page > len(doc):
        doc.close()
        return []

    page_obj = doc[page - 1]
    hits = page_obj.search_for(text)
    doc.close()

    results = []
    for rect in hits:
        box = PdfBox(
            x=float(rect.x0),
            y=float(rect.y0),
            w=float(rect.width),
            h=float(rect.height),
        )
        results.append(box)

    return results


def _find_subsequence(haystack: list[str], needle: list[str]) -> int:
    """Find starting index of needle subsequence in haystack.

    Raises ValueError if needle not found in haystack.
    """
    needle_len = len(needle)
    for i in range(len(haystack) - needle_len + 1):
        if haystack[i : i + needle_len] == needle:
            return i
    raise ValueError("Subsequence not found")


def _extract_target_coords(
    expanded_box: PdfBox, target: str, expanded_text: str
) -> PdfBox | None:
    """Extract coordinates for target portion within expanded match box.

    Approximates target position within expanded text by character ratio.
    Assumes left-to-right text layout.
    """
    target_lower = target.lower()
    expanded_lower = expanded_text.lower()

    start_idx = expanded_lower.find(target_lower)
    if start_idx == -1:
        return None

    char_ratio_start = start_idx / len(expanded_text)
    char_ratio_end = (start_idx + len(target)) / len(expanded_text)

    target_x = expanded_box.x + (expanded_box.w * char_ratio_start)
    target_w = expanded_box.w * (char_ratio_end - char_ratio_start)

    return PdfBox(x=target_x, y=expanded_box.y, w=target_w, h=expanded_box.h)


def _group_rects_by_occurrence(
    rects: list[PdfBox], line_gap: float = 20.0
) -> list[list[PdfBox]]:
    """Group per-line rects from search_for into occurrence groups.

    search_for returns one Rect per visual line of a multi-line match.
    Rects with a vertical gap <= line_gap are consecutive lines of the same
    occurrence. A larger gap means a separate occurrence of the same phrase.
    """
    if not rects:
        return []
    sorted_rects = sorted(rects, key=lambda r: r.y)
    groups: list[list[PdfBox]] = [[sorted_rects[0]]]
    for rect in sorted_rects[1:]:
        prev = groups[-1][-1]
        gap = rect.y - (prev.y + prev.h)
        if gap <= line_gap:
            groups[-1].append(rect)
        else:
            groups.append([rect])
    return groups


def _disambiguate_with_context(
    pdf_path: str, target: str, context: str, page: int, candidates: list[PdfBox]
) -> PdfBox | None:
    """Progressively expand search with context words until unique match.

    Example: target "test" in context "patient received test protocol"
    tries "received test protocol", and if unique, returns coords for "test" only.
    """
    context_words = context.split()
    target_words = target.split()

    try:
        start_idx = _find_subsequence(context_words, target_words)
    except ValueError:
        logger.debug(f"Target '{target}' not found in context")
        return None

    for radius in range(1, min(5, len(context_words))):
        left = max(0, start_idx - radius)
        right = min(len(context_words), start_idx + len(target_words) + radius)

        expanded_words = context_words[left:right]
        expanded_text = " ".join(expanded_words)

        matches = _exact_search(pdf_path, expanded_text, page)

        if len(matches) == 1:
            return _extract_target_coords(matches[0], target, expanded_text)

    logger.debug(f"Could not disambiguate '{target}' with context")
    return None


def _fuzzy_search(
    pdf_path: str, text: str, page: int, threshold: float
) -> PdfBox | None:
    """Fuzzy text matching using similarity ratio.

    Extracts all text blocks from page, finds most similar match.
    Checks up to 5-word combinations.
    """
    doc = fitz.open(pdf_path)

    if page < 1 or page > len(doc):
        doc.close()
        return None

    page_obj = doc[page - 1]
    words = page_obj.get_text("words")

    best_match = None
    best_ratio = 0.0
    best_rect = None

    target_lower = text.lower()

    for i, word in enumerate(words):
        word_text = str(word[4]).lower()

        ratio = SequenceMatcher(None, target_lower, word_text).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = word_text
            best_rect = fitz.Rect(
                float(word[0]), float(word[1]), float(word[2]), float(word[3])
            )

        for j in range(i + 1, min(i + 6, len(words))):
            combined_text = " ".join(
                str(words[k][4]) for k in range(i, j + 1)
            ).lower()
            ratio = SequenceMatcher(None, target_lower, combined_text).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = combined_text
                x0 = min(float(words[k][0]) for k in range(i, j + 1))
                y0 = min(float(words[k][1]) for k in range(i, j + 1))
                x1 = max(float(words[k][2]) for k in range(i, j + 1))
                y1 = max(float(words[k][3]) for k in range(i, j + 1))
                best_rect = fitz.Rect(x0, y0, x1, y1)

    doc.close()

    if best_ratio >= threshold and best_rect:
        logger.debug(
            f"Fuzzy match: '{text}' → '{best_match}' (ratio: {best_ratio:.2f})"
        )
        return PdfBox(
            x=float(best_rect.x0),
            y=float(best_rect.y0),
            w=float(best_rect.width),
            h=float(best_rect.height),
        )

    return None


def find_text_coordinates(
    pdf_path: str,
    target_text: str,
    page_hint: int,
    context: str,
    fuzzy_threshold: float = 0.8,
) -> list[PdfBox]:
    """Find coordinates for LLM-detected text using multi-stage search.

    Strategy:
    1. Exact match on page_hint
    2. If multiple matches: expand with context words until unique
    3. If no exact match: fuzzy search (>= 80% similarity)
    """
    matches = _exact_search(pdf_path, target_text, page_hint)
    groups = _group_rects_by_occurrence(matches)

    if len(groups) == 1:
        return groups[0]

    if len(groups) > 1:
        unique_match = _disambiguate_with_context(
            pdf_path, target_text, context, page_hint, matches
        )
        if unique_match:
            return [unique_match]
        logger.debug(
            f"Disambiguation failed, using first occurrence for '{target_text}'"
        )
        return groups[0]

    fuzzy_match = _fuzzy_search(pdf_path, target_text, page_hint, fuzzy_threshold)
    return [fuzzy_match] if fuzzy_match else []


def find_all_text_coordinates(
    pdf_path: str,
    target_text: str,
    page_hint: int | None = None,
    fuzzy_threshold: float = 0.8,
) -> list[PdfBox]:
    """Find ALL occurrences of text in a PDF document.

    Unlike find_text_coordinates() which returns only the first or contextually
    correct occurrence, this returns ALL occurrences found.

    Useful for amendment matching where the same phrase may legitimately appear
    multiple times and all instances should be redacted.
    """
    if not target_text or not target_text.strip():
        return []

    page = page_hint if page_hint is not None else 1

    matches = _exact_search(pdf_path, target_text, page)
    if matches:
        groups = _group_rects_by_occurrence(matches)

        all_boxes = []
        for group in groups:
            all_boxes.extend(group)

        logger.debug(
            f"Found {len(groups)} occurrence(s) of '{target_text}' "
            f"({len(all_boxes)} total boxes)"
        )
        return all_boxes

    fuzzy_result = _fuzzy_search(pdf_path, target_text, page, fuzzy_threshold)
    if fuzzy_result:
        logger.debug(f"Fuzzy search found 1 box for '{target_text}'")
        return [fuzzy_result]

    logger.debug(f"No matches found for '{target_text}'")
    return []
