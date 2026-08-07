"""PDF rendering and page operations."""

import os
import base64
from collections.abc import Callable
from dataclasses import dataclass

import fitz

from src.core.state.app_state import PdfBox


def list_pdf_files(folder_path: str) -> list[str]:
    """List all PDF files in a folder."""
    if not os.path.exists(folder_path):
        return []
    return [
        os.path.join(folder_path, f)
        for f in os.listdir(folder_path)
        if f.lower().endswith(".pdf")
    ]


def get_pdf_page_data(
    file_path: str, page_index: int, zoom: float, base_width: int
) -> tuple[str | None, float, float, float, int]:
    """Get rendered page image and metadata.

    Returns: (image_data, scale_factor, pdf_width, pdf_height, total_pages)
    """
    if not file_path or not os.path.exists(file_path):
        return None, 1.0, 0, 0, 0

    with fitz.open(file_path) as doc:
        total_pages = len(doc)
        if page_index < 0 or page_index >= total_pages:
            return None, 1.0, 0, 0, total_pages
        page = doc[page_index]
        rect = page.rect
        pdf_w = rect.width
        target_width = base_width * zoom
        scale_factor = target_width / pdf_w if pdf_w > 0 else 1.0
        pix = page.get_pixmap(matrix=fitz.Matrix(scale_factor, scale_factor))
        # Fallback to raw bytes if PNG encoding fails
        try:
            png_bytes = pix.tobytes("png")
            img_data = base64.b64encode(png_bytes).decode("utf-8")
        except Exception:
            img_data = base64.b64encode(pix.tobytes()).decode("utf-8")
        return img_data, scale_factor, pdf_w, rect.height, total_pages


def auto_redact_matches(file_path: str, page_index: int, term: str) -> list[PdfBox]:
    """Find all instances of term on page and return bounding boxes."""
    boxes: list[PdfBox] = []
    with fitz.open(file_path) as doc:
        page = doc[page_index]
        ignore_case = getattr(fitz, "TEXT_SEARCH_IGNORECASE", 0)
        dehyph = getattr(fitz, "TEXT_DEHYPHENATE", 0)
        flags = ignore_case | dehyph
        hits = (
            page.search_for(term, flags=flags) if flags else page.search_for(term)
        )
        for h in hits:
            boxes.append(PdfBox(x=h.x0, y=h.y0, w=h.width, h=h.height))
    return boxes


def save_redacted_pdf(
    file_path: str,
    redactions: dict[int, list[PdfBox]],
    toc_redactions: dict[int, str] | None = None,
    output_dir: str | None = None,
) -> str | None:
    """Save PDF with redaction annotations (hover-to-view style).

    Creates red rectangle annotations and redaction annotations with transparent fill.
    The redaction annots have IC set to black and AP set to null to achieve hover-to-view behavior.

    Returns: Path to saved output PDF, or None if no redactions
    """
    if not redactions and not toc_redactions:
        return None

    with fitz.open(file_path) as doc:
        file_name = os.path.basename(file_path)

        for p_idx, boxes in redactions.items():
            if p_idx >= len(doc):
                continue
            page = doc[p_idx]

            for box in boxes:
                pdf_rect = fitz.Rect(box.x, box.y, box.x + box.w, box.y + box.h)
                stroke_color = (1, 0, 0)
                ic_value = "[0 0 0]"

                square = page.add_rect_annot(pdf_rect)
                square.set_border(width=1.5, style="S")
                square.set_colors(stroke=stroke_color)
                square.update()

                quad = fitz.Quad(pdf_rect.tl, pdf_rect.tr, pdf_rect.bl, pdf_rect.br)
                annot = page.add_redact_annot(quad)
                annot.set_colors(stroke=[], fill=[])
                annot.update()

                doc.xref_set_key(annot.xref, "IC", ic_value)
                doc.xref_set_key(annot.xref, "AP", "null")

        if toc_redactions:
            toc = doc.get_toc(simple=True) or []
            new_toc = []
            for i, item in enumerate(toc):
                lvl, title, page_num = item[0], item[1], item[2]
                if i in toc_redactions:
                    title = toc_redactions[i]
                new_toc.append([lvl, title, page_num])
            doc.set_toc(new_toc)

        if output_dir:
            out_path = os.path.join(output_dir, f"REDACTED_{file_name}")
        else:
            out_path = os.path.join(
                os.path.dirname(file_path), f"REDACTED_{file_name}"
            )
        doc.save(out_path, garbage=4, deflate=False)
        return out_path


@dataclass(slots=True)
class BatchSaveResult:
    """Result of batch PDF save operation."""

    file_name: str
    file_path: str
    output_path: str
    success: bool
    error: str


def _safe_progress_callback(
    callback: Callable[[int, int, str, bool, str], None] | None,
    completed: int,
    total: int,
    filename: str,
    success: bool,
    detail: str,
) -> None:
    if callback:
        try:
            callback(completed, total, filename, success, detail)
        except Exception:
            pass


def _collect_files_to_save(
    all_redactions: dict[str, dict[int, list[PdfBox]]],
    all_toc_redactions: dict[str, dict[int, str]],
) -> set[str]:
    files: set[str] = set()
    for fname, pages in all_redactions.items():
        if any(boxes for boxes in pages.values()):
            files.add(fname)
    for fname, entries in all_toc_redactions.items():
        if entries:
            files.add(fname)
    return files


def _create_file_not_found_result(fname: str, full_path: str | None) -> BatchSaveResult:
    return BatchSaveResult(
        file_name=fname,
        file_path=full_path or "",
        output_path="",
        success=False,
        error=f"File not found: {full_path or fname}",
    )


def _save_single_file(
    fname: str,
    full_path: str,
    page_reds: dict[int, list[PdfBox]],
    toc_reds: dict[int, str],
    output_dir: str | None = None,
) -> BatchSaveResult:
    try:
        out_path = save_redacted_pdf(full_path, page_reds, toc_reds, output_dir)
        success = bool(out_path)
        return BatchSaveResult(
            file_name=fname,
            file_path=full_path,
            output_path=out_path or "",
            success=success,
            error="" if success else "save_redacted_pdf returned None",
        )
    except Exception as e:
        return BatchSaveResult(
            file_name=fname,
            file_path=full_path,
            output_path="",
            success=False,
            error=str(e),
        )


def batch_save_redacted_pdfs(
    all_redactions: dict[str, dict[int, list[PdfBox]]],
    all_toc_redactions: dict[str, dict[int, str]],
    file_path_map: dict[str, str],
    progress_callback: Callable[[int, int, str, bool, str], None] | None = None,
    output_dir: str | None = None,
) -> list[BatchSaveResult]:
    """Save redacted PDFs for every file that has pending redactions or TOC edits."""
    files_to_save = _collect_files_to_save(all_redactions, all_toc_redactions)
    results: list[BatchSaveResult] = []
    total = len(files_to_save)

    if total == 0:
        return results

    for idx, fname in enumerate(sorted(files_to_save)):
        full_path = file_path_map.get(fname)
        if not full_path or not os.path.exists(full_path):
            result = _create_file_not_found_result(fname, full_path)
            results.append(result)
            _safe_progress_callback(
                progress_callback, idx + 1, total, fname, False, result.error
            )
            continue

        page_reds = all_redactions.get(fname, {})
        toc_reds = all_toc_redactions.get(fname, {})
        result = _save_single_file(fname, full_path, page_reds, toc_reds, output_dir)
        results.append(result)

        detail = result.output_path if result.success else result.error
        _safe_progress_callback(
            progress_callback, idx + 1, total, fname, result.success, detail
        )

    return results


def find_bookmark_for_page(file_path: str, page_number: int) -> str | None:
    """Find the bookmark title for a given page number."""
    with fitz.open(file_path) as doc:
        toc = doc.get_toc(simple=True) or []
        last_title = None
        for entry in toc:
            title, pg = entry[1], entry[2]
            if pg <= page_number:
                last_title = title
            elif pg > page_number:
                break
        return last_title


def extract_text_under_rect(file_path: str, page_idx: int, rect: PdfBox) -> str:
    """Extract text under a rectangle from a PDF page."""
    with fitz.open(file_path) as doc:
        if page_idx >= len(doc):
            return ""
        page = doc[page_idx]
        pdf_rect = fitz.Rect(rect.x, rect.y, rect.x + rect.w, rect.y + rect.h)
        text = str(page.get_text("text", clip=pdf_rect)).strip()
        return " ".join(text.split())


def extract_context_around_rect(
    file_path: str,
    page_idx: int,
    rect: PdfBox,
    context_chars: int = 200,
) -> str:
    """Extract text context around a rectangle."""
    with fitz.open(file_path) as doc:
        if page_idx >= len(doc):
            return ""
        page = doc[page_idx]
        full_text = str(page.get_text("text"))
        target_text = extract_text_under_rect(file_path, page_idx, rect)
        if not target_text or target_text not in full_text:
            return target_text

        idx = full_text.find(target_text)
        start = max(0, idx - context_chars)
        end = min(len(full_text), idx + len(target_text) + context_chars)
        return full_text[start:end].strip()
