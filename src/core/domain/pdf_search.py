"""PDF search and text analysis operations.

Handles PDF text search, wildcard matching, context extraction, and highlight text functionality.
"""

import os
import re
from collections.abc import Iterable

import fitz


def preprocess_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def find_term_with_wildcard(term: str, text: str) -> Iterable[re.Match[str]]:
    """Find term in text supporting * wildcards.

    Returns empty list for invalid regex patterns to prevent search failures.
    """
    pattern_parts = [re.escape(part) for part in term.split("*")]
    regex_pattern = r"\b" + r"\w*".join(pattern_parts) + r"\b"
    try:
        return re.compile(regex_pattern, re.IGNORECASE).finditer(text)
    except re.error:
        return []


def extract_sentence_context(
    text: str,
    match_start: int,
    match_end: int,
    min_context: int = 80,
    search_radius: int = 300,
) -> str:
    """Extract sentence context around a match.

    Expands from match to sentence boundaries, ensuring at least min_context characters.
    """
    look_back = text[max(0, match_start - search_radius) : match_start]
    sent_break = -1
    for punct in [". ", "? ", "! ", "; "]:
        idx = look_back.rfind(punct)
        if idx > sent_break:
            sent_break = idx
    if sent_break >= 0:
        ctx_start = max(0, match_start - search_radius) + sent_break + 2
    else:
        ctx_start = max(0, match_start - min_context)

    look_fwd = text[match_end : min(len(text), match_end + search_radius)]
    sent_end = -1
    for punct in [". ", "? ", "! ", "; "]:
        idx = look_fwd.find(punct)
        if idx >= 0 and (sent_end < 0 or idx < sent_end):
            sent_end = idx
    if sent_end >= 0:
        ctx_end = match_end + sent_end + 1
    else:
        ctx_end = min(len(text), match_end + min_context)

    span = ctx_end - ctx_start
    if span < min_context:
        deficit = min_context - span
        ctx_start = max(0, ctx_start - deficit // 2)
        ctx_end = min(len(text), ctx_end + (deficit - deficit // 2))

    return text[ctx_start:ctx_end].strip()


def get_matches_in_page_range(
    file_path: str,
    term: str,
    start_page: int,
    end_page: int,
) -> list[dict[str, str | int]]:
    with fitz.open(file_path) as doc:
        results: list[dict[str, str | int]] = []
        for page_num in range(start_page, min(end_page + 1, len(doc))):
            page = doc[page_num]
            text = str(page.get_text("text"))
            processed = preprocess_text(text)
            matches = find_term_with_wildcard(term, processed)
            for match in matches:
                context = extract_sentence_context(
                    processed, match.start(), match.end()
                )
                results.append(
                    {
                        "file_name": os.path.basename(file_path),
                        "file_path": file_path,
                        "page": page_num + 1,
                        "term": term,
                        "match": match.group(0),
                        "context": context,
                    }
                )
        return results
