"""CCI (Company Confidential Information) dosing detection.

Handles detection of dosing information in PDFs using pattern matching and context analysis.
"""

import re
from dataclasses import dataclass

from src.core.state.app_state import PdfBox

DOSING_UNITS = {
    "mg",
    "g",
    "kg",
    "ng",
    "mcg",
    "ug",
    "µg",
    "mL",
    "ml",
    "L",
    "l",
    "IU",
    "iu",
    "mmol",
    "mEq",
    "meq",
}

# Matches numeric values with optional ranges (e.g., "100", "50-100", "1,000.5")
_NUMERIC_TOKEN_RE = re.compile(
    r"^(?P<num>(?:\d{1,3}(?:,\d{3})*|\d+)(?:[\.,]\d+)?)(?:\s*[-–]\s*(?:\d{1,3}(?:,\d{3})*|\d+)(?:[\.,]\d+)?)?$"
)

# Matches combined dose patterns (e.g., "100mg", "50-100mg/kg")
_COMBINED_DOSE_RE = re.compile(
    r"^(?P<num>(?:\d{1,3}(?:,\d{3})*|\d+)(?:[\.,]\d+)?(?:\s*[-–]\s*(?:\d{1,3}(?:,\d{3})*|\d+)(?:[\.,]\d+)?)?)"
    r"(?P<unit>(?:mg|g|kg|ng|mcg|ug|µg|mL|ml|L|l|IU|iu|mmol|mEq|meq))"
    r"(?P<tail>(?:\/[A-Za-zµ^0-9]+)?)$"
)

# Matches unit tokens with optional per-unit qualifiers (e.g., "mg", "mg/kg")
_UNIT_TOKEN_RE = re.compile(
    r"^(?P<unit>(?:mg|g|kg|ng|mcg|ug|µg|mL|ml|L|l|IU|iu|mmol|mEq|meq))(?:\/[A-Za-zµ^0-9]+)?$"
)

# Patterns for document structure references that shouldn't be flagged as dosing (page numbers, sections, etc.)
_FALSE_POSITIVE_CONTEXT_PATTERNS = [
    re.compile(r"\bpage\s+\d", re.IGNORECASE),
    re.compile(r"\bp\.\s*\d", re.IGNORECASE),
    re.compile(r"\bsection\s+\d", re.IGNORECASE),
    re.compile(r"\btable\s+\d", re.IGNORECASE),
    re.compile(r"\bfigure\s+\d", re.IGNORECASE),
    re.compile(r"\bfig\.\s*\d", re.IGNORECASE),
    re.compile(r"\bappendix\s+\d", re.IGNORECASE),
    re.compile(r"\bchapter\s+\d", re.IGNORECASE),
    re.compile(r"\bversion\s+\d", re.IGNORECASE),
    re.compile(r"\bv\d+\.\d+", re.IGNORECASE),
    re.compile(r"\bitem\s+\d", re.IGNORECASE),
    re.compile(r"\bline\s+\d", re.IGNORECASE),
    re.compile(r"\bref\.\s*\d", re.IGNORECASE),
    re.compile(r"\breference\s+\d", re.IGNORECASE),
]

_DOSING_CONTEXT_KEYWORDS = {
    "dose",
    "doses",
    "dosing",
    "dosage",
    "administered",
    "administer",
    "administration",
    "received",
    "receive",
    "receives",
    "given",
    "give",
    "gives",
    "inject",
    "injected",
    "injection",
    "infuse",
    "infused",
    "infusion",
    "oral",
    "orally",
    "intravenous",
    "iv",
    "subcutaneous",
    "sc",
    "im",
    "daily",
    "weekly",
    "monthly",
    "twice",
    "once",
    "bid",
    "tid",
    "qid",
    "mg/kg",
    "mg/m2",
    "units/kg",
    "tablet",
    "tablets",
    "capsule",
    "capsules",
    "treatment",
    "therapy",
    "regimen",
    "patient",
    "patients",
    "subject",
    "subjects",
    "concentration",
    "plasma",
    "serum",
    "blood",
}


def _is_false_positive_context(context: str) -> bool:
    for pattern in _FALSE_POSITIVE_CONTEXT_PATTERNS:
        if pattern.search(context):
            return True
    return False


def _has_dosing_context_keyword(context: str, proximity_words: int = 8) -> bool:
    context_lower = context.lower()
    for keyword in _DOSING_CONTEXT_KEYWORDS:
        if keyword in context_lower:
            return True
    return False


def _clean_token(token: str) -> str:
    return (token or "").strip().strip("()[]{}<>.,;:!?")


def _union_word_rects(word_rows: list[tuple[float, ...]]) -> PdfBox:
    x0 = min(float(r[0]) for r in word_rows)
    y0 = min(float(r[1]) for r in word_rows)
    x1 = max(float(r[2]) for r in word_rows)
    y1 = max(float(r[3]) for r in word_rows)
    return PdfBox(x=x0, y=y0, w=max(0.0, x1 - x0), h=max(0.0, y1 - y0))


def _group_words_by_line(
    words: list[tuple[float, ...]],
) -> dict[tuple[int, int], list[tuple[float, ...]]]:
    """Group words by (block_no, line_no) to identify visual lines from PyMuPDF tuples."""
    from collections import defaultdict

    lines: dict[tuple[int, int], list[tuple[float, ...]]] = defaultdict(list)
    for w in words:
        block_no = int(w[5])
        line_no = int(w[6])
        lines[(block_no, line_no)].append(w)
    return dict(lines)


def _create_multiline_rects(word_rows: list[tuple[float, ...]]) -> list[PdfBox]:
    """Create multiple rectangles (one per line) for a dose match."""
    if not word_rows:
        return []

    lines_dict = _group_words_by_line(word_rows)

    rects: list[PdfBox] = []
    for line_words in lines_dict.values():
        if line_words:
            rect = _union_word_rects(line_words)
            rects.append(rect)

    return rects


@dataclass(slots=True)
class DosingMatch:
    match: str
    context: str
    rects: list[PdfBox]


def _extract_dosing_matches_from_words(
    words: list[tuple[float, ...]],
    *,
    context_window_words: int = 8,
    smart_filter: bool = False,
    require_dosing_context: bool = False,
) -> list[DosingMatch]:
    """Extract dosing matches from PyMuPDF word tuples.

    smart_filter: If True, exclude document structure references (page/section numbers)
    require_dosing_context: If True, only include matches near clinical dosing keywords
    """
    if context_window_words < 0:
        raise ValueError("context_window_words must be >= 0")
    if not words:
        return []

    ordered = sorted(words, key=lambda r: (int(r[5]), int(r[6]), int(r[7])))
    tokens = [str(r[4]) for r in ordered]

    results: list[DosingMatch] = []
    seen: set[tuple[int, int]] = set()

    def build_context(start_idx: int, end_idx: int) -> str:
        left = max(0, start_idx - context_window_words)
        right = min(len(tokens), end_idx + context_window_words + 1)
        return " ".join(tokens[left:right]).strip()

    def should_include(context: str) -> bool:
        if smart_filter and _is_false_positive_context(context):
            return False
        if require_dosing_context and not _has_dosing_context_keyword(context):
            return False
        return True

    i = 0
    while i < len(ordered):
        cleaned = _clean_token(tokens[i])
        if not cleaned:
            i += 1
            continue

        if _COMBINED_DOSE_RE.match(cleaned):
            if (i, i) not in seen:
                seen.add((i, i))
                context = build_context(i, i)
                if should_include(context):
                    results.append(
                        DosingMatch(
                            match=cleaned,
                            context=context,
                            rects=_create_multiline_rects([ordered[i]]),
                        )
                    )
            i += 1
            continue

        if _NUMERIC_TOKEN_RE.match(cleaned) and (i + 1) < len(ordered):
            nxt = _clean_token(tokens[i + 1])
            if nxt and _UNIT_TOKEN_RE.match(nxt):
                if (i, i + 1) not in seen:
                    seen.add((i, i + 1))
                    context = build_context(i, i + 1)
                    if should_include(context):
                        results.append(
                            DosingMatch(
                                match=f"{cleaned} {nxt}",
                                context=context,
                                rects=_create_multiline_rects(
                                    [ordered[i], ordered[i + 1]]
                                ),
                            )
                        )
                i += 2
                continue

        i += 1

    return results
