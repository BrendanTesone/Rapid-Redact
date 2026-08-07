"""Detect text redacted in some places but not others."""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

import fitz

if TYPE_CHECKING:
    from src.core.state.app_state import RedactionBox

logger = logging.getLogger(__name__)

ProjectRedactionsDict = dict[str, dict[int, list["RedactionBox"]]]


@dataclass(slots=True)
class RedactedRect:
    x: float
    y: float
    w: float
    h: float


@dataclass(slots=True)
class RedactedLocation:
    file_name: str
    page: int


@dataclass(slots=True)
class ConsistencyGap:
    file_name: str
    file_path: str
    page: int
    match_text: str
    context: str
    redacted_locations: list[tuple[str, int]]
    gap_type: str
    rect: RedactedRect | None = None

    def to_dict(
        self,
    ) -> dict[str, str | int | list[dict[str, str | int]] | dict[str, float] | None]:
        rect_dict: dict[str, float] | None = None
        if self.rect:
            rect_dict = {
                "x": self.rect.x,
                "y": self.rect.y,
                "w": self.rect.w,
                "h": self.rect.h,
            }

        return {
            "file_name": self.file_name,
            "file_path": self.file_path,
            "page": self.page,
            "match_text": self.match_text,
            "context": self.context,
            "redacted_locations": [
                {"file_name": loc[0], "page": loc[1]} for loc in self.redacted_locations
            ],
            "gap_type": self.gap_type,
            "rect": rect_dict,
        }


@dataclass(slots=True)
class ConsistencyCache:
    scan_results: dict[tuple[str, int, str], list[ConsistencyGap]]
    scanned_files: set[str]
    scanned_texts: set[str]
    file_page_combinations: set[tuple[str, int]]


_consistency_cache: ConsistencyCache = ConsistencyCache(
    scan_results={},
    scanned_files=set(),
    scanned_texts=set(),
    file_page_combinations=set(),
)


def _extract_text_with_threshold(
    page: object,
    box_rect: object,
    overlap_threshold: float = 0.5,
) -> str:
    """Extract text where >= overlap_threshold of each word's area is covered by box."""
    words: list[object] = page.get_text("words")  # type: ignore[attr-defined]
    qualifying_words: list[str] = []

    for w in words:
        word_rect = fitz.Rect(float(w[0]), float(w[1]), float(w[2]), float(w[3]))  # type: ignore[index]
        word_area = word_rect.width * word_rect.height

        if word_area <= 0:
            continue

        intersection = word_rect & box_rect
        if intersection.is_empty:
            continue

        intersection_area = intersection.width * intersection.height
        coverage = intersection_area / word_area

        if coverage >= overlap_threshold:
            qualifying_words.append(str(w[4]))  # type: ignore[index]

    return " ".join(qualifying_words)


def _extract_text_under_box(
    doc: object,
    page_index: int,
    box: RedactionBox,
    text_overlap_threshold: float = 0.5,
) -> str:
    if page_index < 0 or page_index >= len(doc):  # type: ignore[arg-type]
        return ""

    page = doc[page_index]  # type: ignore[index]
    box_rect = fitz.Rect(
        float(box.x),
        float(box.y),
        float(box.x + box.w),
        float(box.y + box.h),
    )

    return _extract_text_with_threshold(page, box_rect, text_overlap_threshold)


def _extract_file_metadata(
    file_paths: list[str],
    project_redactions: ProjectRedactionsDict,
    text_overlap_threshold: float = 0.5,
) -> tuple[
    dict[str, set[str]],
    set[tuple[str, int]],
    dict[str, list[tuple[str, int]]],
]:
    """Extract metadata in single pass: redacted texts, file/page combos, redaction locations."""
    redacted_texts: dict[str, set[str]] = defaultdict(set)
    file_page_combinations: set[tuple[str, int]] = set()
    text_to_redacted_locs: dict[str, list[tuple[str, int]]] = defaultdict(list)

    for path in file_paths:
        if not path or not os.path.exists(path):
            continue

        fname = os.path.basename(path)
        file_redactions = project_redactions.get(fname, {})

        try:
            with fitz.open(path) as doc:
                for page_idx in range(len(doc)):
                    file_page_combinations.add((fname, page_idx))

                if file_redactions:
                    text_to_pages: dict[str, set[int]] = defaultdict(set)

                    for page_idx, boxes in file_redactions.items():
                        for box in boxes:
                            text = _extract_text_under_box(
                                doc, page_idx, box, text_overlap_threshold
                            )
                            normalized_text = text.strip()
                            if normalized_text:
                                redacted_texts[fname].add(normalized_text)
                                text_to_pages[normalized_text.lower()].add(page_idx)

                    for text, pages in text_to_pages.items():
                        for page_idx in pages:
                            text_to_redacted_locs[text].append((fname, page_idx + 1))

        except Exception as exc:
            logger.warning(f"Error processing {fname}: {exc}")

    return redacted_texts, file_page_combinations, text_to_redacted_locs


def _is_location_redacted(
    file_name: str,
    page_idx: int,
    hit_rect: object,
    project_redactions: ProjectRedactionsDict,
    overlap_threshold: float = 0.5,
) -> bool:
    file_redactions = project_redactions.get(file_name, {})
    boxes = file_redactions.get(page_idx, [])

    hit_area = hit_rect.width * hit_rect.height  # type: ignore[attr-defined]
    if hit_area <= 0:
        return False

    for box in boxes:
        box_rect = fitz.Rect(
            float(box.x),
            float(box.y),
            float(box.x + box.w),
            float(box.y + box.h),
        )

        intersection = hit_rect & box_rect
        if intersection.is_empty:
            continue

        intersection_area = intersection.width * intersection.height
        coverage = intersection_area / hit_area
        if coverage >= overlap_threshold:
            return True

    return False


def _build_redaction_boxes_index(
    fname: str,
    page_idx: int,
    project_redactions: ProjectRedactionsDict,
) -> list[object]:
    file_redactions = project_redactions.get(fname, {})
    boxes = file_redactions.get(page_idx, [])

    rects: list[object] = []
    for box in boxes:
        rect = fitz.Rect(
            float(box.x),
            float(box.y),
            float(box.x + box.w),
            float(box.y + box.h),
        )
        rects.append(rect)

    return rects


def _is_hit_redacted_fast(
    hit_rect: object,
    redaction_rects: list[object],
    overlap_threshold: float = 0.5,
) -> bool:
    hit_area = hit_rect.width * hit_rect.height  # type: ignore[attr-defined]
    if hit_area <= 0:
        return False

    for box_rect in redaction_rects:
        intersection = hit_rect & box_rect  # type: ignore[operator]
        if intersection.is_empty:
            continue

        intersection_area = intersection.width * intersection.height
        coverage = intersection_area / hit_area
        if coverage >= overlap_threshold:
            return True

    return False


def _extract_context_from_words(
    words: list[object],
    hit_rect: object,
    context_radius: float = 200.0,
) -> str:
    context_rect = fitz.Rect(
        hit_rect.x0 - context_radius,  # type: ignore[attr-defined]
        hit_rect.y0 - 5,  # type: ignore[attr-defined]
        hit_rect.x1 + context_radius,  # type: ignore[attr-defined]
        hit_rect.y1 + 5,  # type: ignore[attr-defined]
    )

    context_words: list[str] = []
    for w in words:
        word_rect = fitz.Rect(float(w[0]), float(w[1]), float(w[2]), float(w[3]))  # type: ignore[index]
        if not (word_rect & context_rect).is_empty:
            context_words.append(str(w[4]))  # type: ignore[index]

    context = " ".join(context_words)
    return re.sub(r"\s+", " ", context)[:300]


def _is_whole_word_match(hit_text: str, search_text: str) -> bool:
    """Reject substring matches - only accept whole word boundaries."""
    hit_normalized = re.sub(r"\s+", " ", hit_text.strip()).lower()
    search_normalized = search_text.strip().lower()

    if hit_normalized == search_normalized:
        return True

    pattern = r"\b" + re.escape(search_normalized) + r"\b"
    return bool(re.search(pattern, hit_normalized, re.IGNORECASE))


def _merge_adjacent_rects(
    hits: list[object], max_gap: float = 10.0
) -> list[object]:
    """Merge adjacent rectangles from multi-word search (max_gap in PDF units)."""
    if len(hits) <= 1:
        return hits

    sorted_hits = sorted(hits, key=lambda r: (r.y0, r.x0))  # type: ignore[attr-defined]
    merged: list[object] = []
    current = sorted_hits[0]

    for next_rect in sorted_hits[1:]:
        same_line = abs(current.y0 - next_rect.y0) < 5  # type: ignore[attr-defined]
        close_horizontally = next_rect.x0 - current.x1 <= max_gap  # type: ignore[attr-defined]

        if same_line and close_horizontally:
            current = fitz.Rect(
                current.x0,  # type: ignore[attr-defined]
                current.y0,  # type: ignore[attr-defined]
                max(current.x1, next_rect.x1),  # type: ignore[attr-defined]
                max(current.y1, next_rect.y1),  # type: ignore[attr-defined]
            )
        else:
            merged.append(current)
            current = next_rect

    merged.append(current)
    return merged


def _scan_file_pages(
    fpath: str,
    fname: str,
    pages_to_scan: dict[int, list[str]],
    project_redactions: ProjectRedactionsDict,
    text_to_redacted_locs: dict[str, list[tuple[str, int]]],
    min_text_length: int,
    cancel_flag: Callable[[], bool] | None = None,
) -> dict[tuple[str, int, str], list[ConsistencyGap]]:
    """Scan multiple pages in single file. Opens PDF once, extracts words once per page,
    pre-builds redaction index per page. Thread-safe (PyMuPDF releases GIL)."""

    def is_cancelled() -> bool:
        return cancel_flag is not None and cancel_flag()

    results: dict[tuple[str, int, str], list[ConsistencyGap]] = {}

    if is_cancelled():
        return results

    with fitz.open(fpath) as doc:
        for page_idx, search_texts in pages_to_scan.items():
            if is_cancelled():
                break

            if page_idx < 0 or page_idx >= len(doc):
                continue

            page = doc[page_idx]

            try:
                page_words: list[object] = page.get_text("words")
            except Exception:
                page_words = []

            redaction_rects = _build_redaction_boxes_index(
                fname, page_idx, project_redactions
            )

            for search_text in search_texts:
                if is_cancelled():
                    break

                if len(search_text) < min_text_length:
                    results[(fname, page_idx, search_text)] = []
                    continue

                try:
                    ignore_case = getattr(fitz, "TEXT_SEARCH_IGNORECASE", 0)
                    dehyph = getattr(fitz, "TEXT_DEHYPHENATE", 0)
                    flags = ignore_case | dehyph
                    hits: list[object] = (
                        page.search_for(search_text, flags=flags)
                        if flags
                        else page.search_for(search_text)
                    )
                    hits = _merge_adjacent_rects(hits)

                    validated_hits = []
                    for hit_rect in hits:
                        hit_text = page.get_textbox(hit_rect).strip()
                        if _is_whole_word_match(hit_text, search_text):
                            validated_hits.append(hit_rect)
                    hits = validated_hits
                except Exception:
                    hits = []

                page_gaps: list[ConsistencyGap] = []
                for hit_rect in hits:
                    if _is_hit_redacted_fast(hit_rect, redaction_rects):
                        continue

                    try:
                        context = _extract_context_from_words(
                            page_words, hit_rect
                        ) if page_words else search_text
                    except Exception:
                        context = search_text

                    gap = ConsistencyGap(
                        file_name=fname,
                        file_path=fpath,
                        page=page_idx + 1,
                        match_text=search_text,
                        context=context,
                        redacted_locations=text_to_redacted_locs.get(
                            search_text.lower(), []
                        ),
                        gap_type="deep_scan_gap",
                        rect=RedactedRect(
                            x=hit_rect.x0,  # type: ignore[attr-defined]
                            y=hit_rect.y0,  # type: ignore[attr-defined]
                            w=hit_rect.width,  # type: ignore[attr-defined]
                            h=hit_rect.height,  # type: ignore[attr-defined]
                        ),
                    )
                    page_gaps.append(gap)

                results[(fname, page_idx, search_text)] = page_gaps

    return results


def _optimal_page_worker_count(page_count: int) -> int:
    """PyMuPDF releases GIL during C operations - cap at cpu_count to avoid thrashing."""
    cpu = os.cpu_count() or 4
    return max(1, min(page_count, cpu))


def deep_consistency_scan(
    file_paths: list[str],
    project_redactions: ProjectRedactionsDict,
    min_text_length: int = 3,
    text_overlap_threshold: float = 0.5,
    progress_callback: Callable[[int, int, str], None] | None = None,
    throttled: bool = False,
    cancel_flag: Callable[[], bool] | None = None,
    gap_callback: Callable[[ConsistencyGap], None] | None = None,
) -> list[ConsistencyGap]:
    """Extract text from redaction boxes, search corpus for unredacted occurrences.
    Uses incremental caching and parallel page processing."""

    def is_cancelled() -> bool:
        return cancel_flag is not None and cancel_flag()

    valid_paths = [
        p
        for p in (file_paths or [])
        if isinstance(p, str) and os.path.exists(p) and p.lower().endswith(".pdf")
    ]

    if not valid_paths:
        return []

    if is_cancelled():
        return []

    if progress_callback:
        progress_callback(0, 3, "Analyzing PDFs...")

    import time

    start_time = time.time()
    redacted_texts, current_file_pages, text_to_redacted_locs = _extract_file_metadata(
        valid_paths, project_redactions, text_overlap_threshold=text_overlap_threshold
    )
    extract_time = time.time() - start_time
    logger.info(f"Metadata extraction took {extract_time:.2f}s")

    if is_cancelled():
        return []

    all_unique_texts: set[str] = set()
    for texts in redacted_texts.values():
        all_unique_texts.update(t.lower() for t in texts if len(t) >= min_text_length)

    current_files = set(os.path.basename(p) for p in valid_paths)

    new_files = current_files - _consistency_cache.scanned_files
    new_texts = all_unique_texts - _consistency_cache.scanned_texts
    new_file_pages = current_file_pages - _consistency_cache.file_page_combinations

    valid_cached_results: list[ConsistencyGap] = []
    for key, cached_gaps in _consistency_cache.scan_results.items():
        file_name, page_idx, search_text = key
        if (
            file_name in current_files
            and search_text in all_unique_texts
            and (file_name, page_idx) in current_file_pages
        ):
            valid_cached_results.extend(cached_gaps)

    scan_work: list[tuple[str, int, str]] = []

    for fname in new_files:
        fpath = next((p for p in valid_paths if os.path.basename(p) == fname), None)
        if fpath and os.path.exists(fpath):
            with fitz.open(fpath) as doc:
                for page_idx in range(len(doc)):
                    for search_text in all_unique_texts:
                        scan_work.append((fname, page_idx, search_text))

    for fname, page_idx in current_file_pages:
        for search_text in new_texts:
            if fname not in new_files:
                scan_work.append((fname, page_idx, search_text))

    for fname, page_idx in new_file_pages:
        if fname not in new_files:
            for search_text in all_unique_texts:
                scan_work.append((fname, page_idx, search_text))

    scan_work = list(set(scan_work))

    logger.info(
        f"Consistency scan: {len(scan_work)} operations "
        f"({len(new_files)} new files, {len(new_texts)} new texts, "
        f"{len(new_file_pages)} new pages, {len(valid_cached_results)} cached gaps)"
    )

    if not scan_work:
        logger.info("No new changes detected, using cached results")
        return valid_cached_results

    work_by_file: dict[str, dict[int, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for fname, page_idx, search_text in scan_work:
        work_by_file[fname][page_idx].append(search_text)

    file_count = len(work_by_file)
    total_pages = sum(len(pages) for pages in work_by_file.values())
    logger.info(
        f"Will scan {file_count} files ({total_pages} pages), parallel={file_count >= 3}"
    )

    if progress_callback:
        progress_callback(1, 3, f"Scanning {total_pages} pages...")

    gaps: list[ConsistencyGap] = list(valid_cached_results)
    new_cache_entries: dict[tuple[str, int, str], list[ConsistencyGap]] = {}

    scan_start = time.time()

    if file_count < 3:
        for work_idx, (fname, pages_dict) in enumerate(work_by_file.items()):
            if is_cancelled():
                logger.debug("Consistency scan cancelled")
                break

            fpath = next((p for p in valid_paths if os.path.basename(p) == fname), None)
            if not fpath:
                continue

            file_results = _scan_file_pages(
                fpath,
                fname,
                pages_dict,
                project_redactions,
                text_to_redacted_locs,
                min_text_length,
                cancel_flag,
            )

            new_cache_entries.update(file_results)
            for page_gaps in file_results.values():
                gaps.extend(page_gaps)
                if gap_callback is not None:
                    for gap in page_gaps:
                        try:
                            gap_callback(gap)
                        except Exception:
                            pass

            if progress_callback:
                progress_callback(
                    work_idx + 1,
                    file_count,
                    f"Scanned {work_idx + 1}/{file_count} files",
                )
    else:
        from concurrent.futures import Future, ThreadPoolExecutor, as_completed

        max_workers = _optimal_page_worker_count(file_count)
        completed = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file: dict[
                Future[dict[tuple[str, int, str], list[ConsistencyGap]]], str
            ] = {}
            for fname, pages_dict in work_by_file.items():
                fpath = next(
                    (p for p in valid_paths if os.path.basename(p) == fname), None
                )
                if not fpath:
                    continue

                future = executor.submit(
                    _scan_file_pages,
                    fpath,
                    fname,
                    pages_dict,
                    project_redactions,
                    text_to_redacted_locs,
                    min_text_length,
                    cancel_flag,
                )
                future_to_file[future] = fname

            for future in as_completed(future_to_file):
                if is_cancelled():
                    for f in future_to_file:
                        f.cancel()
                    logger.debug("Consistency scan cancelled")
                    break

                fname = future_to_file[future]
                completed += 1

                try:
                    file_results = future.result()
                    new_cache_entries.update(file_results)

                    for page_gaps in file_results.values():
                        gaps.extend(page_gaps)
                        if gap_callback is not None:
                            for gap in page_gaps:
                                try:
                                    gap_callback(gap)
                                except Exception:
                                    pass

                except Exception as exc:
                    logger.warning(f"Error processing {fname}: {exc}")

                if progress_callback:
                    progress_callback(
                        completed,
                        file_count,
                        f"Scanned {completed}/{file_count} files",
                    )

    scan_time = time.time() - scan_start
    logger.info(f"Scan complete: {len(gaps)} total gaps found in {scan_time:.2f}s")

    _consistency_cache.scan_results.update(new_cache_entries)
    _consistency_cache.scanned_files = current_files
    _consistency_cache.scanned_texts = all_unique_texts
    _consistency_cache.file_page_combinations = current_file_pages

    total_time = time.time() - start_time
    logger.info(
        f"Total consistency scan: {total_time:.2f}s (extract: {extract_time:.2f}s, scan: {scan_time:.2f}s)"
    )

    if progress_callback:
        progress_callback(3, 3, "Consistency scan complete")

    return gaps
