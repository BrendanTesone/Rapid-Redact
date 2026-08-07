"""
Amendment redaction transfer controller.

Handles loading redline PDFs and extracting redaction annotations.
"""

from __future__ import annotations

import traceback
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

if TYPE_CHECKING:
    from src.controllers.main_controller import MainController
    from src.controllers.ai.llm_client import LiteLLMClient

try:
    import fitz  # PyMuPDF

    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

from src.core.state.app_state import PdfBox, RedactionBox, SelectionMode
from src.controllers.amendment.image_amendment import (
    DrawingClusterInfo,
    DrawingClusterRedaction,
)
from src.ui.dialogs import parse_pages_spec
from src.controllers.amendment.extract_and_identify import (
    DrawingClusterDetector,
)
from src.controllers.amendment.match_and_place import (
    DrawingClusterMatcher,
    DrawingClusterTransferer,
)


class AmendmentController:
    """Controller for amendment redaction transfer feature."""

    def __init__(self, main_controller: MainController) -> None:
        self.main = main_controller
        self.state = main_controller.state.amendment
        self.page = main_controller.page
        self._llm_client: LiteLLMClient | None = None
        self._redline_picker: ft.FilePicker = ft.FilePicker(
            on_result=self._on_redline_picked
        )
        self._destination_picker: ft.FilePicker = ft.FilePicker(
            on_result=self._on_destination_picked
        )

    def _get_llm_client(self) -> LiteLLMClient | None:
        if self._llm_client is None:
            try:
                from src.controllers.ai.llm_client import LiteLLMClient

                self._llm_client = LiteLLMClient(self.main.config.ai_api)
            except Exception as e:
                print(f"Failed to initialize LLM client: {e}")
                return None
        return self._llm_client

    def pick_redline_pdf(self) -> None:
        self._redline_picker.pick_files(
            allowed_extensions=["pdf"],
            allow_multiple=False,
            dialog_title="Select Redline PDF",
        )

    def pick_destination_pdf(self) -> None:
        self._destination_picker.pick_files(
            allowed_extensions=["pdf"],
            allow_multiple=False,
            dialog_title="Select Destination PDF",
        )

    def _on_redline_picked(self, e: ft.FilePickerResultEvent) -> None:
        if not e.files:
            return
        file_path = e.files[0].path
        if not file_path:
            return
        self._load_redline_pdf(file_path)

    def _on_destination_picked(self, e: ft.FilePickerResultEvent) -> None:
        if not e.files:
            return
        file_path = e.files[0].path
        if not file_path:
            return
        self._load_destination_pdf(file_path)

    def _load_redline_pdf(self, file_path: str) -> None:
        if not HAS_FITZ:
            self._show_error("PyMuPDF not available")
            return

        self.state.redline_pdf_path = file_path
        self.state.redline_pdf_name = Path(file_path).name
        self.state.extracted_redactions.clear()
        self.state.extraction_error = None
        self.state.extraction_status = "pending"

        try:
            doc = fitz.open(file_path)
            self.state.total_pages = len(doc)
            self.state.redline_page_count = len(doc)
            doc.close()
        except Exception as e:
            self.state.total_pages = 0
            self.state.redline_page_count = 0
            self._show_error(f"Failed to open PDF: {e}")
            return

        self._calculate_page_offset()
        self._show_success(
            f"Loaded {self.state.redline_pdf_name} ({self.state.total_pages} pages)"
        )

        from src.ui.views.amendment import amendment_transfer_view

        amendment_transfer_view.refresh_view(self.main)

    def extract_and_interpret_all(self) -> None:
        if not self.state.redline_pdf_path:
            print("ERROR: No redline PDF loaded")
            return

        from src.ui.views.amendment import amendment_transfer_view
        from src.controllers.amendment.Refactor.cont_refactored import (
            extract_and_interpret_all as do_extract_and_interpret_all,
        )

        print("\nExtracting and interpreting from redline PDF...")

        all_interpreted, total_pages = do_extract_and_interpret_all(
            self.state.redline_pdf_path,
            progress_callback=amendment_transfer_view.update_progress,
        )

        self.state.extracted_redactions = all_interpreted
        self.state.total_pages = total_pages

        total_redactions = sum(len(boxes) for boxes in all_interpreted.values())
        print(f"\nCompleted: {total_redactions} redactions from {total_pages} pages")

        amendment_transfer_view.hide_progress()
        amendment_transfer_view.refresh_view(self.main)

    def extract_current_page(self) -> None:
        from src.core.state.ui_state import refs
        from src.controllers.amendment.Refactor.extract_refactor import (
            print_redline_coords,
        )

        page_field_ref = refs.get("amendment_debug_page_field")
        if not page_field_ref or not page_field_ref.current:
            print("ERROR: Page field not found")
            return

        if not self.state.redline_pdf_path:
            print("ERROR: No redline PDF loaded")
            return

        pages_str = page_field_ref.current.value or "1"
        try:
            page_indices = parse_pages_spec(pages_str, self.state.redline_page_count)
        except ValueError as e:
            self._show_error(f"Invalid page range: {e}")
            return

        for page_idx in page_indices:
            page_num = page_idx + 1
            print(f"\n{'='*60}")
            print(f"EXTRACT: Page {page_num}")
            print(f"{'='*60}")
            print_redline_coords(self.state.redline_pdf_path, page_num)

    def extract_interpret_transfer_page(self) -> None:
        from src.core.state.ui_state import refs

        page_field_ref = refs.get("amendment_debug_page_field")
        if not page_field_ref or not page_field_ref.current:
            print("ERROR: Page field not found")
            return

        if not self.state.redline_pdf_path:
            print("ERROR: No redline PDF loaded")
            return

        if not self.main.state.viewer.file_path:
            self._show_error("No document loaded in viewer.")
            return

        pages_str = page_field_ref.current.value or "1"
        self._extract_interpret_transfer_pages(pages_str)

    def extract_and_interpret_current_page(self) -> None:
        from src.core.state.ui_state import refs
        from src.ui.views.amendment import amendment_transfer_view
        from src.controllers.amendment.Refactor.cont_refactored import (
            extract_and_interpret_page,
        )

        page_field_ref = refs.get("amendment_debug_page_field")
        if not page_field_ref or not page_field_ref.current:
            print("ERROR: Page field not found")
            return

        if not self.state.redline_pdf_path:
            print("ERROR: No redline PDF loaded")
            return

        pages_str = page_field_ref.current.value or "1"
        try:
            page_indices = parse_pages_spec(pages_str, self.state.redline_page_count)
        except ValueError as e:
            self._show_error(f"Invalid page range: {e}")
            return

        all_interpreted = {}

        for page_idx in page_indices:
            page_num = page_idx + 1
            print(f"\nExtracting and interpreting page {page_num}...")

            interpreted_boxes, _ = extract_and_interpret_page(
                self.state.redline_pdf_path, page_num
            )

            all_interpreted[page_idx] = interpreted_boxes

            print(
                f"Extracted and interpreted {len(interpreted_boxes)} redactions from page {page_num}"
            )

        self.state.extracted_redactions = all_interpreted
        self.state.total_pages = len(page_indices)

        amendment_transfer_view.refresh_view(self.main)

        total_boxes = sum(len(boxes) for boxes in all_interpreted.values())
        print(f"\nTotal: {total_boxes} redactions from {len(page_indices)} page(s)")

    def debug_extract_and_match_page(self) -> None:
        from src.core.state.ui_state import refs

        page_field_ref = refs.get("amendment_debug_page_field")
        if not page_field_ref or not page_field_ref.current:
            self._show_error("Page field not found")
            return

        try:
            page_num = int(page_field_ref.current.value or "0")
            if page_num < 1:
                self._show_error("Page number must be >= 1")
                return
        except ValueError:
            self._show_error("Invalid page number")
            return

        page_idx = page_num - 1

        print("\n" + "=" * 80)
        print(f"DEBUG: EXTRACT AND MATCH PAGE {page_num}")
        print("=" * 80)

        if not self.state.redline_pdf_path:
            print("ERROR: No redline PDF loaded")
            self._show_error("No redline PDF loaded")
            return

        if not self.main.state.viewer.file_path:
            print("ERROR: No viewer document loaded")
            self._show_error("No document loaded in viewer")
            return

        if not HAS_FITZ:
            print("ERROR: PyMuPDF not available")
            self._show_error("PyMuPDF not available")
            return

        viewer_path = self.main.state.viewer.file_path
        viewer_name = self.main.state.viewer.file_name

        print(f"\nRedline PDF: {self.state.redline_pdf_path}")
        print(f"Viewer document: {viewer_name}")
        print(f"Target page: {page_num} (index {page_idx})")
        print("-" * 80)

        doc = fitz.open(self.state.redline_pdf_path)
        if page_idx >= len(doc):
            print(f"ERROR: Page {page_num} doesn't exist (PDF has {len(doc)} pages)")
            self._show_error(
                f"Page {page_num} doesn't exist (PDF has {len(doc)} pages)"
            )
            doc.close()
            return

        page = doc[page_idx]
        print(f"\nExtracting redactions from page {page_num}...")
        redactions = self._extract_page_redactions(page, page_idx)
        doc.close()

        print(f"✓ Found {len(redactions)} redaction(s) on page {page_num}")
        print("-" * 80)

        if not redactions:
            print("No redactions to transfer")
            self._show_warning(f"No redactions found on page {page_num}")
            return

        self.state.transfer_stats = {
            "matched": 0,
            "missed": 0,
            "total": len(redactions),
        }

        print(f"\nTransferring {len(redactions)} redaction(s) to viewer...\n")

        first_transferred_page: int | None = None

        for i, redaction in enumerate(redactions, 1):
            print(f"[{i}/{len(redactions)}] Transferring redaction...")
            print(f"  Type: {redaction.term}")
            print(f"  Position: x={redaction.x:.2f}, y={redaction.y:.2f}")
            print(f"  Size: w={redaction.w:.2f}, h={redaction.h:.2f}")

            if redaction.term == "TABLE":
                print("  → Using table-based transfer (OLD - DEPRECATED)")
                transferred_page = self._transfer_table_redaction(
                    redaction, page_idx, viewer_path, viewer_name or ""
                )
            elif redaction.term == "DRAWING_CLUSTER":
                print("  → Using drawing cluster transfer (OLD - DEPRECATED)")
                transferred_page = self._transfer_drawing_cluster_redaction(
                    redaction, page_idx, viewer_path, viewer_name or ""
                )
            else:
                print("  → Using Refactor text-based transfer (NEW)")
                transferred_page = self._transfer_single_redaction_refactor(
                    redaction, page_idx, viewer_path, viewer_name or ""
                )

            if transferred_page is not None and first_transferred_page is None:
                first_transferred_page = transferred_page

            print()

        matched = self.state.transfer_stats["matched"]
        missed = self.state.transfer_stats["missed"]

        print("=" * 80)
        print(f"DEBUG TRANSFER COMPLETE: Page {page_num}")
        print("=" * 80)
        print(f"Matched: {matched}/{len(redactions)}")
        print(f"Missed: {missed}/{len(redactions)}")
        print("=" * 80 + "\n")

        self._show_success(
            f"Transferred {matched} of {len(redactions)} redactions from page {page_num}"
        )

        if first_transferred_page is not None and viewer_path:
            self.main.viewer.navigate_to_page(viewer_path, first_transferred_page)

    def debug_extract_page_only(self) -> None:
        from src.core.state.ui_state import refs

        page_field_ref = refs.get("amendment_debug_page_field")
        if not page_field_ref or not page_field_ref.current:
            self._show_error("Page field not found")
            return

        try:
            page_num = int(page_field_ref.current.value or "0")
            if page_num < 1:
                self._show_error("Page number must be >= 1")
                return
        except ValueError:
            self._show_error("Invalid page number")
            return

        page_idx = page_num - 1

        print("\n" + "=" * 80)
        print(f"DEBUG: EXTRACT PAGE {page_num} ONLY")
        print("=" * 80)

        if not self.state.redline_pdf_path:
            print("ERROR: No redline PDF loaded")
            self._show_error("No redline PDF loaded")
            return

        if not HAS_FITZ:
            print("ERROR: PyMuPDF not available")
            self._show_error("PyMuPDF not available")
            return

        print(f"\nRedline PDF: {self.state.redline_pdf_path}")
        print(f"Target page: {page_num} (index {page_idx})")
        print("-" * 80)

        doc = fitz.open(self.state.redline_pdf_path)
        if page_idx >= len(doc):
            print(f"ERROR: Page {page_num} doesn't exist (PDF has {len(doc)} pages)")
            self._show_error(
                f"Page {page_num} doesn't exist (PDF has {len(doc)} pages)"
            )
            doc.close()
            return

        page = doc[page_idx]
        print(f"\nExtracting redactions from page {page_num}...")
        redactions = self._extract_page_redactions(page, page_idx)
        doc.close()

        print(f"\n{'='*80}")
        print(f"EXTRACTION RESULTS - Page {page_num}")
        print(f"{'='*80}\n")
        print(f"Total redactions extracted: {len(redactions)}")

        table_count = sum(1 for r in redactions if r.term == "TABLE")
        drawing_count = sum(1 for r in redactions if r.term == "DRAWING_CLUSTER")
        text_count = len(redactions) - table_count - drawing_count

        print(f"  - Table redactions: {table_count}")
        print(f"  - Drawing cluster redactions: {drawing_count}")
        print(f"  - Text redactions: {text_count}")

        if redactions:
            print(f"\n{'─'*80}")
            print("DETAILED BREAKDOWN")
            print(f"{'─'*80}\n")

            for i, redaction in enumerate(redactions, 1):
                print(f"[{i}/{len(redactions)}] {redaction.term}")
                print(f"    Position: ({redaction.x:.1f}, {redaction.y:.1f})")
                print(f"    Size: {redaction.w:.1f} x {redaction.h:.1f}")

                if redaction.match:
                    try:
                        if redaction.term == "TABLE":
                            from src.controllers.amendment.image_amendment import (
                                TableRedaction,
                            )

                            table_data = TableRedaction.from_json(redaction.match)
                            if table_data.center_cell:
                                print(
                                    f"    Cell text: '{table_data.center_cell.cell_text[:60]}...'"
                                )
                                print(
                                    f"    Offset: ({table_data.center_cell.offset_x:.2f}, {table_data.center_cell.offset_y:.2f})"
                                )
                        elif redaction.term == "DRAWING_CLUSTER":
                            from src.controllers.amendment.image_amendment import (
                                DrawingClusterRedaction,
                            )

                            drawing_data = DrawingClusterRedaction.from_json(
                                redaction.match
                            )
                            print(f"    Drawing count: {drawing_data.drawing_count}")
                            print(
                                f"    Overlap: {drawing_data.overlap_percentage:.1%}"
                            )
                    except Exception as e:
                        print(f"    (Failed to parse match data: {e})")

                print()

        self._show_success(
            f"Extracted {len(redactions)} redactions from page {page_num} (see console)"
        )

    def debug_extract_page_57_text(self) -> None:
        print("\n" + "=" * 80)
        print("DEBUG: EXTRACTING TEXT FROM PAGE 57 REDACTIONS")
        print("=" * 80)

        if not self.state.redline_pdf_path:
            print("ERROR: No redline PDF loaded")
            self._show_error("No redline PDF loaded")
            return

        if not HAS_FITZ:
            print("ERROR: PyMuPDF not available")
            self._show_error("PyMuPDF not available")
            return

        page_idx = 56

        print(f"\nRedline PDF: {self.state.redline_pdf_path}")
        print(f"Page number: 57 (index {page_idx})")
        print("Opening PDF and extracting page 57...")
        print("-" * 80)

        doc = fitz.open(self.state.redline_pdf_path)
        if page_idx >= len(doc):
            print(f"ERROR: Page 57 doesn't exist (PDF has {len(doc)} pages)")
            self._show_error(f"Page 57 doesn't exist (PDF has {len(doc)} pages)")
            doc.close()
            return

        page = doc[page_idx]
        print(f"Extracting redactions from page {page_idx + 1}...")
        redactions = self._extract_page_redactions(page, page_idx)
        doc.close()

        print(f"Total redactions found on page: {len(redactions)}")
        print("-" * 80)

        if not redactions:
            print("No redactions found on page 57")
            self._show_warning("No redactions found on page 57")
            return

        from src.core.domain.pdf_rendering import extract_text_under_rect

        for i, redaction in enumerate(redactions, 1):
            print(f"\n{'='*80}")
            print(f"REDACTION #{i} of {len(redactions)}")
            print(f"{'='*80}")
            print(f"Position: x={redaction.x:.2f}, y={redaction.y:.2f}")
            print(f"Size: w={redaction.w:.2f}, h={redaction.h:.2f}")
            print(f"Term: {redaction.term}")
            print(f"Selection mode: {redaction.selection_mode}")

            if redaction.match:
                print("\nPre-extracted text (from match):")
                print(f"  Length: {len(redaction.match)} characters")
                print(f"  Content: '{redaction.match}'")
            else:
                print("\nNo pre-extracted text in match field")

            print("\nExtracting text from bounding box:")
            box = PdfBox(x=redaction.x, y=redaction.y, w=redaction.w, h=redaction.h)
            extracted_text = extract_text_under_rect(
                self.state.redline_pdf_path, page_idx, box
            )
            print(f"  Length: {len(extracted_text)} characters")
            print(f"  Content: '{extracted_text}'")

            if redaction.match and extracted_text:
                if redaction.match == extracted_text:
                    print("  ✓ Matches pre-extracted text")
                else:
                    print("  ⚠️  DIFFERS from pre-extracted text!")
                    print(f"     Pre-extracted: '{redaction.match}'")
                    print(f"     Box-extracted: '{extracted_text}'")

        print("\n" + "=" * 80)
        print(f"EXTRACTION COMPLETE: {len(redactions)} redactions processed")
        print("=" * 80 + "\n")

        self._show_success(
            f"Extracted text from {len(redactions)} redactions on page 57 (check console)"
        )

    def extract_all_redactions(self) -> None:
        if not self.state.redline_pdf_path:
            self._show_error("No redline PDF loaded. Select a redline PDF first.")
            return

        if not HAS_FITZ:
            self._show_error("PyMuPDF not available")
            return

        self.state.extraction_status = "loading"
        self.state.extracted_redactions.clear()

        doc = fitz.open(self.state.redline_pdf_path)
        total_pages = len(doc)

        from src.ui.views.amendment import amendment_transfer_view

        total_redactions = 0
        for page_idx in range(total_pages):
            amendment_transfer_view.update_progress(
                page_idx + 1,
                total_pages,
                f"Extracting page {page_idx + 1} of {total_pages}",
            )

            page = doc[page_idx]
            page_redactions = self._extract_page_redactions(page, page_idx)

            if page_redactions:
                self.state.extracted_redactions[page_idx] = page_redactions
                total_redactions += len(page_redactions)

        amendment_transfer_view.hide_progress()

        doc.close()

        self.state.extraction_status = "success"

        print(f"\n{'='*60}")
        print(f"Extracted Redactions from: {self.state.redline_pdf_name}")
        print(f"{'='*60}")
        print(f"Total Pages: {self.state.total_pages}")
        print(f"Total Redactions: {total_redactions}")
        print("\nRedactions by Page:")
        print(f"{'-'*60}")

        for page_idx in sorted(self.state.extracted_redactions.keys()):
            redactions = self.state.extracted_redactions[page_idx]
            print(f"  Page {page_idx + 1}: {len(redactions)} redaction(s)")
            for i, box in enumerate(redactions, 1):
                print(
                    f"    [{i}] x={box.x:.2f}, y={box.y:.2f}, "
                    f"w={box.w:.2f}, h={box.h:.2f}"
                )

        print(f"{'='*60}\n")

        self._show_success(
            f"Extracted {total_redactions} redactions from {self.state.total_pages} pages"
        )

        from src.ui.views.amendment import amendment_transfer_view

        amendment_transfer_view.refresh_view(self.main)

    def _extract_page_redactions(
        self, page: fitz.Page, page_idx: int
    ) -> list:  # type: ignore[type-arg]
        """Extract redaction annotations using 4 detection passes:
        1. Type 25 (Official Redact), 2. Subject='Redact', 3. Subject contains 'redact', 4. Type 13 (Stamp)
        Each pass runs separately to avoid conflicts and enable debugging.
        """

        redactions = []

        def should_extract_pass1(annot_type: int, subject: str) -> bool:
            return annot_type == 25

        def should_extract_pass2(annot_type: int, subject: str) -> bool:
            return subject == "Redact"

        def should_extract_pass3(annot_type: int, subject: str) -> bool:
            return "redact" in subject.lower()

        def should_extract_pass4(annot_type: int, subject: str) -> bool:
            return annot_type == 13

        detection_methods = [
            (should_extract_pass1, "Type 25 (Official Redact)"),
            (should_extract_pass2, "Subject='Redact' (Exact)"),
            (should_extract_pass3, "Subject contains 'redact'"),
            (should_extract_pass4, "Type 13 (Stamp)"),
        ]

        seen_annot_ids: set[int] = set()

        for pass_num, (detection_func, method_name) in enumerate(detection_methods, 1):
            annot = page.first_annot
            while annot:
                annot_id = id(annot)
                if annot_id in seen_annot_ids:
                    annot = annot.next
                    continue

                annot_type = annot.type[0]
                subject = annot.info.get("subject", "").strip()

                if not detection_func(annot_type, subject):
                    annot = annot.next
                    continue

                seen_annot_ids.add(annot_id)

                extracted_boxes = self._extract_redaction(annot, page, page_idx)
                for box in extracted_boxes:
                    box.term = f"{method_name}"
                    redactions.append(box)

                annot = annot.next

        from src.controllers.amendment.extract_and_identify import TableDetector

        table_detector = TableDetector()
        drawing_detector = DrawingClusterDetector()
        redactions_to_add = []

        for redaction in redactions:
            redaction_rect = fitz.Rect(
                redaction.x,
                redaction.y,
                redaction.x + redaction.w,
                redaction.y + redaction.h,
            )

            table_overlap = table_detector.detect_table_overlap(page, redaction_rect)
            if table_overlap:
                redaction.term = "TABLE"
                redaction.match = table_overlap.to_json()
                print(
                    f"  📊 Table redaction detected: {table_overlap.overlap_percentage:.0%} overlap at page {page_idx + 1}"
                )
                continue

            cluster_overlap = drawing_detector.detect_drawing_overlaps(
                page, redaction_rect
            )
            if cluster_overlap:
                redaction.term = "DRAWING_CLUSTER"
                redaction.match = cluster_overlap.to_json()
                print(
                    f"  ✏️  Drawing cluster overlap detected: {cluster_overlap.overlap_percentage:.0%} "
                    f"coverage, {cluster_overlap.drawing_count} drawings at page {page_idx + 1}"
                )

                if drawing_detector.has_text_content(page, redaction_rect):
                    text_redaction = RedactionBox(
                        id=str(uuid.uuid4()),
                        x=redaction.x,
                        y=redaction.y,
                        w=redaction.w,
                        h=redaction.h,
                        page=redaction.page,
                        selection_mode=redaction.selection_mode,
                        match="",
                        term="",
                        batch_id=None,
                    )
                    redactions_to_add.append(text_redaction)
                    print(
                        "       ℹ️  Also creating separate text redaction for text content"
                    )
                continue

            redaction.term = ""

        redactions.extend(redactions_to_add)

        return redactions

    def _extract_redaction(
        self, annot: fitz.Annot, page: fitz.Page, page_idx: int
    ) -> list[RedactionBox]:
        """Multi-line (8+ vertices): one box/line. Single-line (4 vertices): one box. Rectangle: split by text lines."""
        if not HAS_FITZ:
            return []

        vertices = annot.vertices if hasattr(annot, "vertices") else None

        if vertices:
            num_lines = len(vertices) // 4

            if num_lines >= 2:
                return self._extract_multiline_as_separate_boxes(
                    annot, page, page_idx, vertices
                )
            else:
                box = self._extract_single_line_from_vertices(
                    annot, page, page_idx, vertices
                )
                return [box] if box else []
        else:
            return self._extract_rect_split_by_text_lines(annot, page, page_idx)

    def _extract_multiline_as_separate_boxes(
        self, annot: fitz.Annot, page: fitz.Page, page_idx: int, vertices: list  # type: ignore[type-arg]
    ) -> list[RedactionBox]:
        num_lines = len(vertices) // 4
        line_boxes = []

        for line_idx in range(num_lines):
            line_vertices = vertices[line_idx * 4 : (line_idx + 1) * 4]

            x_coords = [v[0] for v in line_vertices]
            y_coords = [v[1] for v in line_vertices]
            min_x, max_x = min(x_coords), max(x_coords)
            min_y, max_y = min(y_coords), max(y_coords)

            line_rect = fitz.Rect(min_x, min_y, max_x, max_y)
            line_text = page.get_text("text", clip=line_rect).strip()
            line_text = " ".join(line_text.split())

            line_box = RedactionBox(
                id=str(uuid.uuid4()),
                x=float(min_x),
                y=float(min_y),
                w=float(max_x - min_x),
                h=float(max_y - min_y),
                page=page_idx + 1,
                selection_mode=SelectionMode.HIGHLIGHT,
                term="redline",
                match=line_text,
                batch_id=None,
            )
            line_boxes.append(line_box)

        return line_boxes

    def _extract_single_line_from_vertices(
        self, annot: fitz.Annot, page: fitz.Page, page_idx: int, vertices: list  # type: ignore[type-arg]
    ) -> RedactionBox | None:
        if len(vertices) != 4:
            return None

        x_coords = [v[0] for v in vertices]
        y_coords = [v[1] for v in vertices]
        min_x, max_x = min(x_coords), max(x_coords)
        min_y, max_y = min(y_coords), max(y_coords)

        rect = fitz.Rect(min_x, min_y, max_x, max_y)
        text = page.get_text("text", clip=rect).strip()
        text = " ".join(text.split())

        return RedactionBox(
            id=str(uuid.uuid4()),
            x=float(min_x),
            y=float(min_y),
            w=float(max_x - min_x),
            h=float(max_y - min_y),
            page=page_idx + 1,
            selection_mode=SelectionMode.HIGHLIGHT,
            term="redline",
            match=text,
            batch_id=None,
        )

    def _extract_rect_split_by_text_lines(
        self, annot: fitz.Annot, page: fitz.Page, page_idx: int
    ) -> list[RedactionBox]:
        """For rectangles, extract text block structure and create one box per text line."""
        rect = annot.rect

        text_blocks = page.get_text("dict", clip=rect)

        line_boxes = []
        for block in text_blocks.get("blocks", []):
            if block.get("type") == 0:
                for line in block.get("lines", []):
                    line_bbox = line.get("bbox")
                    if not line_bbox:
                        continue

                    x0, y0, x1, y1 = line_bbox

                    line_text = " ".join(
                        span.get("text", "") for span in line.get("spans", [])
                    ).strip()

                    if not line_text:
                        continue

                    line_box = RedactionBox(
                        id=str(uuid.uuid4()),
                        x=float(x0),
                        y=float(y0),
                        w=float(x1 - x0),
                        h=float(y1 - y0),
                        page=page_idx + 1,
                        selection_mode=SelectionMode.HIGHLIGHT,
                        term="redline",
                        match=line_text,
                        batch_id=None,
                    )
                    line_boxes.append(line_box)

        if not line_boxes:
            text = page.get_text("text", clip=rect).strip()
            text = " ".join(text.split())

            line_boxes.append(
                RedactionBox(
                    id=str(uuid.uuid4()),
                    x=float(rect.x0),
                    y=float(rect.y0),
                    w=float(rect.x1 - rect.x0),
                    h=float(rect.y1 - rect.y0),
                    page=page_idx + 1,
                    selection_mode=SelectionMode.HIGHLIGHT,
                    term="redline",
                    match=text,
                    batch_id=None,
                )
            )

        return line_boxes

    def _show_error(self, message: str) -> None:
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor="red",
        )
        self.page.snack_bar.open = True
        self.page.update()

    def _show_success(self, message: str) -> None:
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor="green",
        )
        self.page.snack_bar.open = True
        self.page.update()

    def _show_warning(self, message: str) -> None:
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor="orange",
        )
        self.page.snack_bar.open = True
        self.page.update()

    def transfer_single_page(self) -> None:
        from src.core.state.ui_state import refs

        page_input_ref = refs.get("amendment_single_page_input")
        if not page_input_ref or not page_input_ref.current:
            self._show_error("Page input not found")
            return

        page_input = page_input_ref.current.value
        if not page_input:
            self._show_error("Please enter a page number")
            return

        try:
            page_num = int(page_input)
            page_idx = page_num - 1
        except ValueError:
            self._show_error("Invalid page number")
            return

        if not self.state.extracted_redactions:
            self._show_error("No redactions loaded. Select a redline PDF first.")
            return

        if page_idx not in self.state.extracted_redactions:
            self._show_error(f"No redactions found on page {page_num}")
            return

        if not self.main.state.viewer.file_path:
            self._show_error("No document loaded in viewer.")
            return

        viewer_path = self.main.state.viewer.file_path
        viewer_name = self.main.state.viewer.file_name

        self.state.transfer_status = "running"
        self.state.transfer_stats = {"matched": 0, "missed": 0, "total": 0}

        redactions = self.state.extracted_redactions[page_idx]
        self.state.transfer_stats["total"] = len(redactions)

        print(f"\n{'='*60}")
        print(f"TRANSFER: Single Page {page_num}")
        print(f"{'='*60}")
        print(f"Redline PDF: {self.state.redline_pdf_name}")
        print(f"Viewer document: {viewer_name}")
        print(f"Processing page {page_num}: {len(redactions)} redaction(s)")
        print(f"{'-'*60}\n")

        from src.ui.views.amendment import amendment_transfer_view

        amendment_transfer_view.update_progress(
            0, len(redactions), "Starting transfer..."
        )

        first_transferred_page = None

        for i, redaction in enumerate(redactions, 1):
            print(f"  [{i}/{len(redactions)}] Transferring redaction...")

            amendment_transfer_view.update_progress(
                i, len(redactions), f"Transferring {i}/{len(redactions)}..."
            )

            if redaction.term == "TABLE":
                transferred_page = self._transfer_table_redaction(
                    redaction, page_idx, viewer_path, viewer_name or ""
                )
            elif redaction.term == "DRAWING_CLUSTER":
                transferred_page = self._transfer_drawing_cluster_redaction(
                    redaction, page_idx, viewer_path, viewer_name or ""
                )
            else:
                transferred_page = self._transfer_single_redaction_refactor(
                    redaction, page_idx, viewer_path, viewer_name or ""
                )

            if transferred_page is not None and first_transferred_page is None:
                first_transferred_page = transferred_page

        print()

        amendment_transfer_view.hide_progress()

        self.state.transfer_status = "success"
        matched = self.state.transfer_stats["matched"]
        missed = self.state.transfer_stats["missed"]

        print(f"{'='*60}")
        print(f"TRANSFER: Page {page_num} Complete")
        print(f"{'='*60}")
        print(f"Matched: {matched}/{len(redactions)}")
        print(f"Missed: {missed}/{len(redactions)}")
        print(f"{'='*60}\n")

        self._show_success(
            f"Transferred {matched} of {len(redactions)} redactions from page {page_num}"
        )

        if first_transferred_page is not None and viewer_path:
            self.main.viewer.navigate_to_page(viewer_path, first_transferred_page)

    def transfer_redactions_to_viewer(self) -> None:
        """Extract, interpret, and transfer ALL pages from redline to viewer."""
        if not self.state.redline_pdf_path:
            self._show_error("No redline PDF loaded.")
            return

        if not self.main.state.viewer.file_path:
            self._show_error("No destination document loaded.")
            return

        total_pages = self.state.redline_page_count
        if total_pages == 0:
            self._show_error("Redline PDF has no pages.")
            return

        page_range_str = f"1-{total_pages}"
        print(f"Processing all pages: {page_range_str}")

        self._extract_interpret_transfer_pages(page_range_str)

    def _extract_interpret_transfer_pages(self, pages_str: str) -> None:
        """Internal method to extract, interpret, and transfer specified pages."""
        from src.ui.views.amendment import amendment_transfer_view
        from src.controllers.amendment.Refactor.cont_refactored import (
            extract_and_interpret_page,
        )

        viewer_path = self.main.state.viewer.file_path
        viewer_name = self.main.state.viewer.file_name

        if not viewer_path or not self.state.redline_pdf_path:
            self._show_error("Missing viewer or redline PDF path")
            return

        try:
            page_indices = parse_pages_spec(pages_str, self.state.redline_page_count)
        except ValueError as e:
            self._show_error(f"Invalid page range: {e}")
            return

        try:
            total_matched = 0
            total_missed = 0
            total_redactions_all = 0
            first_transferred_page = None

            for page_idx in page_indices:
                page_num = page_idx + 1

                print(f"\n{'='*60}")
                print(f"EXTRACT, INTERPRET & TRANSFER: Page {page_num}")
                print(f"{'='*60}")

                interpreted_boxes, _ = extract_and_interpret_page(
                    self.state.redline_pdf_path, page_num
                )

                page_redactions = len(interpreted_boxes)
                total_redactions_all += page_redactions

                print(
                    f"Extracted and interpreted {page_redactions} redactions from page {page_num}"
                )

                if page_redactions == 0:
                    print("No redactions found on this page")
                    continue

                self.state.transfer_stats = {
                    "matched": 0,
                    "missed": 0,
                    "total": page_redactions,
                }

                text_boxes = []
                other_boxes = []

                for box in interpreted_boxes:
                    if box.term == "TEXT":
                        text_boxes.append(box)
                    else:
                        other_boxes.append(box)

                if text_boxes:
                    print(f"  Batch AI matching {len(text_boxes)} TEXT redaction(s)...")
                    transferred_page = self._transfer_text_batch_ai(
                        text_boxes, page_idx, viewer_path, viewer_name or ""
                    )

                    if transferred_page is not None and first_transferred_page is None:
                        first_transferred_page = transferred_page

                # for i, box in enumerate(other_boxes, 1):
                #     print(f"  [{i}/{len(other_boxes)}] Transferring {box.term} redaction...")

                #     if box.term == "TABLE":
                #         transferred_page = self._transfer_table_redaction(
                #             box, page_idx, viewer_path, viewer_name or ""
                #         )
                #     elif box.term == "DRAWING_CLUSTER":
                #         transferred_page = self._transfer_drawing_cluster_redaction(
                #             box, page_idx, viewer_path, viewer_name or ""
                #         )

                #     if transferred_page is not None and first_transferred_page is None:
                #         first_transferred_page = transferred_page

                total_matched += self.state.transfer_stats["matched"]
                total_missed += self.state.transfer_stats["missed"]

            print(f"\n{'='*60}")
            print(f"TRANSFER COMPLETE: {len(page_indices)} page(s)")
            print(f"{'='*60}")
            print(f"Matched: {total_matched}/{total_redactions_all}")
            print(f"Missed: {total_missed}/{total_redactions_all}")
            print(f"{'='*60}\n")

            self._show_success(
                f"{len(page_indices)} page(s): {total_matched}/{total_redactions_all} matched, {total_missed} missed"
            )

            if first_transferred_page is not None:
                print(
                    f"Navigating to first transferred redaction on page {first_transferred_page}..."
                )
                self.main.viewer.navigate_to_page(viewer_path, first_transferred_page)

        except Exception as e:
            print(f"ERROR: Failed to extract, interpret, and transfer: {e}")
            import traceback

            traceback.print_exc()
            amendment_transfer_view.hide_progress()
            self._show_error(f"Failed: {e}")

    def _transfer_single_redaction(
        self,
        redaction: RedactionBox,
        redline_page_idx: int,
        viewer_path: str,
        viewer_name: str,
    ) -> int | None:
        if not self.state.redline_pdf_path:
            print("    ❌ ERROR: No redline PDF loaded")
            self._show_warning("No redline PDF loaded")
            self.state.transfer_stats["missed"] += 1
            return None

        if redaction.match:
            text = redaction.match
            print(f"    📝 Using pre-extracted text: '{text[:60]}...'")
        else:
            from src.core.domain.pdf_rendering import extract_text_under_rect

            box = PdfBox(x=redaction.x, y=redaction.y, w=redaction.w, h=redaction.h)
            text = extract_text_under_rect(
                self.state.redline_pdf_path, redline_page_idx, box
            )
            print(f"    📝 Extracted text: '{text[:60]}...'")

        if not text or len(text) < 3:
            print(f"    ⊘ SKIP: Empty/tiny text (len={len(text)})")
            self.state.transfer_stats["missed"] += 1
            return None

        print("    🔍 Searching viewer document...")
        matched_boxes = self._find_text_in_viewer(
            text, viewer_path, redline_page_idx
        )

        if not matched_boxes:
            print("    ⚠️  MISS: Text not found in viewer document")
            self._show_warning(f"Text not found: '{text[:50]}...'")
            self.state.transfer_stats["missed"] += 1
            return None

        print(f"    ✓ FOUND: {len(matched_boxes)} match(es)")

        first_page = None
        total_added = 0

        for page_idx, line_boxes in matched_boxes:
            page_num = page_idx + 1

            min_x = min(box.x for box in line_boxes)
            min_y = min(box.y for box in line_boxes)
            max_x = max(box.x + box.w for box in line_boxes)
            max_y = max(box.y + box.h for box in line_boxes)

            combined_box = PdfBox(
                x=float(min_x),
                y=float(min_y),
                w=float(max_x - min_x),
                h=float(max_y - min_y),
            )

            is_multiline = combined_box.h > 20
            selection_mode = (
                SelectionMode.RECTANGLE if is_multiline else SelectionMode.HIGHLIGHT
            )

            print(
                f"       Match on page {page_num} covering {len(line_boxes)} line(s), "
                f"height={combined_box.h:.1f}pt, mode={'RECTANGLE' if is_multiline else 'HIGHLIGHT'}"
            )

            if self._overlaps_existing_redaction(
                combined_box, page_idx, viewer_name or ""
            ):
                print(
                    f"         ⊘ SKIP: Overlaps existing at ({combined_box.x:.1f}, {combined_box.y:.1f})"
                )
                continue

            print(
                f"         → Creating redaction at ({combined_box.x:.1f}, {combined_box.y:.1f})"
            )

            new_redaction = RedactionBox(
                id=str(uuid.uuid4()),
                x=combined_box.x,
                y=combined_box.y,
                w=combined_box.w,
                h=combined_box.h,
                page=page_idx,
                selection_mode=selection_mode,
                match=text,
                term="redline_transfer",
            )
            self.main.redaction_data.add_redaction_internal(
                new_redaction, page_idx, viewer_name
            )

            self.main.viewer.navigate_to_page(viewer_name, page_num)

            if first_page is None:
                first_page = page_num
            total_added += 1

        if total_added > 0:
            self.state.transfer_stats["matched"] += total_added
            print(f"    ✓ SUCCESS: {total_added} redaction(s) transferred")
            return first_page
        else:
            self.state.transfer_stats["missed"] += 1
            print("    ⚠️  MISS: All matches overlapped with existing redactions")
            return None

    def _transfer_single_redaction_refactor(
        self,
        redaction: RedactionBox,
        redline_page_idx: int,
        viewer_path: str,
        viewer_name: str,
    ) -> int | None:
        """Transfer a single redaction using NEW Refactor matching code.

        Args:
            redaction: Redaction box from redline PDF
            redline_page_idx: Page index in redline PDF (0-based)
            viewer_path: Path to viewer document
            viewer_name: Filename of viewer document

        Returns:
            1-based page number of match, or None if no match
        """
        if not HAS_FITZ:
            self.state.transfer_stats["missed"] += 1
            return None

        # Route to appropriate matcher based on redaction type
        if redaction.term == "TABLE":
            return self._transfer_table_refactor(
                redaction, redline_page_idx, viewer_path, viewer_name
            )
        elif redaction.term == "DRAWING_CLUSTER":
            return self._transfer_drawing_refactor(
                redaction, redline_page_idx, viewer_path, viewer_name
            )
        else:
            return self._transfer_text_refactor(
                redaction, redline_page_idx, viewer_path, viewer_name
            )

    def _transfer_table_refactor(
        self,
        redaction: RedactionBox,
        redline_page_idx: int,
        viewer_path: str,
        viewer_name: str,
    ) -> int | None:
        """Transfer table redaction using Refactor matching."""
        from src.core.state.app_state import TableRedactionBox
        from src.controllers.amendment.Refactor.match_table_refactor import match_table

        if not isinstance(redaction, TableRedactionBox):
            print("    ⊘ SKIP: TABLE redaction but not TableRedactionBox type")
            self.state.transfer_stats["missed"] += 1
            return None

        try:
            viewer_doc = fitz.open(viewer_path)

            matched_box = match_table(
                redaction,
                viewer_doc,
                redline_page_idx,
                page_offset=(
                    abs(self.state.page_offset) if self.state.page_offset != 0 else 2
                ),
            )

            viewer_doc.close()

            if not matched_box:
                print("    ⚠️  MISS: Table not found in viewer document")
                self.state.transfer_stats["missed"] += 1
                return None

            print(f"    ✓ FOUND: Table match on page {matched_box.page}")

            if self._overlaps_existing_redaction(
                PdfBox(
                    x=matched_box.x,
                    y=matched_box.y,
                    w=matched_box.w,
                    h=matched_box.h,
                ),
                matched_box.page - 1,
                viewer_name,
            ):
                print("    ⊘ SKIP: Overlaps existing redaction")
                self.state.transfer_stats["missed"] += 1
                return None

            print(
                f"    → Creating table redaction on page {matched_box.page} at ({matched_box.x:.1f}, {matched_box.y:.1f})"
            )

            new_redaction = RedactionBox(
                id=str(uuid.uuid4()),
                x=matched_box.x,
                y=matched_box.y,
                w=matched_box.w,
                h=matched_box.h,
                page=matched_box.page - 1,
                selection_mode=matched_box.selection_mode,
                match="",
                term="redline_transfer",
            )

            self.main.redaction_data.add_redaction_internal(
                new_redaction, matched_box.page - 1, viewer_name
            )

            self.state.transfer_stats["matched"] += 1
            return matched_box.page

        except Exception as e:
            print(f"    ⚠️  ERROR: {e}")
            self.state.transfer_stats["missed"] += 1
            return None

    def _transfer_drawing_refactor(
        self,
        redaction: RedactionBox,
        redline_page_idx: int,
        viewer_path: str,
        viewer_name: str,
    ) -> int | None:
        """Transfer drawing redaction using Refactor matching."""
        print("    ⊘ SKIP: Drawing cluster matching not yet implemented in Refactor")
        self.state.transfer_stats["missed"] += 1
        return None

    def _transfer_text_refactor(
        self,
        redaction: RedactionBox,
        redline_page_idx: int,
        viewer_path: str,
        viewer_name: str,
    ) -> int | None:
        """Transfer text redaction using Refactor matching."""
        try:
            from src.controllers.amendment.Refactor.match_text_refactor import (
                match_text,
            )

            if not redaction.match or len(redaction.match) < 3:
                print(f"    ⊘ SKIP: Empty/tiny text (len={len(redaction.match or '')})")
                self.state.transfer_stats["missed"] += 1
                return None

            print(f"    📝 Matching text: '{redaction.match[:60]}...'")

            viewer_doc = fitz.open(viewer_path)
            redline_doc = fitz.open(self.state.redline_pdf_path)
            llm_client = self._get_llm_client()

            matched_boxes = match_text(
                redaction,
                viewer_doc,
                redline_page_idx,
                page_offset=(
                    abs(self.state.page_offset) if self.state.page_offset != 0 else 2
                ),
                llm_client=llm_client,
                source_doc=redline_doc,
            )

            viewer_doc.close()
            redline_doc.close()

            if not matched_boxes:
                print("    ⚠️  MISS: Text not found in viewer document")
                self.state.transfer_stats["missed"] += 1
                return None

            print(f"    ✓ FOUND: {len(matched_boxes)} match(es)")

            first_page = None
            added_count = 0

            for matched_box in matched_boxes:
                page_num = matched_box.page

                if self._overlaps_existing_redaction(
                    PdfBox(
                        x=matched_box.x,
                        y=matched_box.y,
                        w=matched_box.w,
                        h=matched_box.h,
                    ),
                    matched_box.page - 1,
                    viewer_name,
                ):
                    print(
                        f"         ⊘ SKIP: Overlaps existing at page {page_num} ({matched_box.x:.1f}, {matched_box.y:.1f})"
                    )
                    continue

                print(
                    f"         → Creating redaction on page {page_num} at ({matched_box.x:.1f}, {matched_box.y:.1f})"
                )

                new_redaction = RedactionBox(
                    id=str(uuid.uuid4()),
                    x=matched_box.x,
                    y=matched_box.y,
                    w=matched_box.w,
                    h=matched_box.h,
                    page=matched_box.page - 1,
                    selection_mode=matched_box.selection_mode,
                    match=redaction.match,
                    term="redline_transfer",
                )

                self.main.redaction_data.add_redaction_internal(
                    new_redaction, matched_box.page - 1, viewer_name
                )

                if first_page is None:
                    first_page = page_num

                added_count += 1

            if added_count > 0:
                self.state.transfer_stats["matched"] += added_count
                print(f"    ✓ SUCCESS: {added_count} redaction(s) transferred")
                return first_page
            else:
                print("    ⚠️  MISS: All matches overlapped with existing redactions")
                self.state.transfer_stats["missed"] += 1
                return None

        except Exception as e:
            print(f"    ❌ ERROR: Failed to transfer: {e}")
            traceback.print_exc()
            self.state.transfer_stats["missed"] += 1
            return None

    def _transfer_text_batch_ai(
        self,
        text_boxes: list[RedactionBox],
        redline_page_idx: int,
        viewer_path: str,
        viewer_name: str,
    ) -> int | None:
        """Transfer batch of TEXT redactions using AI matching."""
        if not text_boxes:
            return None

        try:
            from src.controllers.amendment.Refactor.ai_match_text import (
                ai_match_text_batch,
            )

            viewer_doc = fitz.open(viewer_path)
            redline_doc = fitz.open(self.state.redline_pdf_path)
            llm_client = self._get_llm_client()

            if not llm_client:
                print(
                    "    ⚠️  LLM client not available, falling back to individual matching"
                )
                for redaction in text_boxes:
                    self._transfer_text_refactor(
                        redaction, redline_page_idx, viewer_path, viewer_name
                    )
                return None

            page_offset = (
                abs(self.state.page_offset) if self.state.page_offset != 0 else 2
            )

            print(f"    🤖 AI matching {len(text_boxes)} text redactions...")

            matched_boxes = ai_match_text_batch(
                text_boxes=text_boxes,
                source_doc=redline_doc,
                dest_doc=viewer_doc,
                source_page_idx=redline_page_idx,
                page_offset=page_offset,
                llm_client=llm_client,
            )

            viewer_doc.close()
            redline_doc.close()

            if not matched_boxes:
                print("    ⚠️  MISS: No matches found")
                self.state.transfer_stats["missed"] += len(text_boxes)
                return None

            print(f"    ✓ FOUND: {len(matched_boxes)} match(es)")

            first_page = None
            added_count = 0

            for matched_box in matched_boxes:
                page_num = matched_box.page

                if self._overlaps_existing_redaction(
                    PdfBox(
                        x=matched_box.x,
                        y=matched_box.y,
                        w=matched_box.w,
                        h=matched_box.h,
                    ),
                    matched_box.page - 1,
                    viewer_name,
                ):
                    print(
                        f"         ⊘ SKIP: Overlaps existing at page {page_num} ({matched_box.x:.1f}, {matched_box.y:.1f})"
                    )
                    continue

                print(
                    f"         → Creating redaction on page {page_num} at ({matched_box.x:.1f}, {matched_box.y:.1f})"
                )

                new_redaction = RedactionBox(
                    id=str(uuid.uuid4()),
                    x=matched_box.x,
                    y=matched_box.y,
                    w=matched_box.w,
                    h=matched_box.h,
                    page=matched_box.page - 1,
                    selection_mode=matched_box.selection_mode,
                    match=matched_box.match,
                    term="redline_transfer",
                )

                self.main.redaction_data.add_redaction_internal(
                    new_redaction, matched_box.page - 1, viewer_name
                )

                if first_page is None:
                    first_page = page_num

                added_count += 1

            if added_count > 0:
                self.state.transfer_stats["matched"] += added_count
                print(f"    ✓ SUCCESS: {added_count} redaction(s) transferred")
            else:
                print("    ⚠️  MISS: All matches overlapped with existing redactions")

            missed_count = len(text_boxes) - added_count
            if missed_count > 0:
                self.state.transfer_stats["missed"] += missed_count

            return first_page

        except Exception as e:
            print(f"    ❌ ERROR: Batch AI transfer failed: {e}")
            traceback.print_exc()
            self.state.transfer_stats["missed"] += len(text_boxes)
            return None

    def _transfer_drawing_cluster_redaction(
        self,
        redaction: RedactionBox,
        redline_page_idx: int,
        viewer_path: str,
        viewer_name: str,
    ) -> int | None:
        """
        Transfer drawing-cluster-based redaction using cluster matching.

        Args:
            redaction: Redaction box from redline PDF
            redline_page_idx: Page index in redline PDF (0-based)
            viewer_path: Path to viewer PDF
            viewer_name: Viewer filename

        Returns:
            1-based page number if transferred, None if missed
        """
        if not HAS_FITZ:
            self.state.transfer_stats["missed"] += 1
            return None

        try:
            # Parse stored cluster data
            if not redaction.match:
                self.state.transfer_stats["missed"] += 1
                return None

            cluster_data = DrawingClusterRedaction.from_json(redaction.match)

            print(
                f"    🔍 Searching for drawing cluster ({cluster_data.drawing_count} drawings, "
                f"{cluster_data.overlap_percentage:.0%} overlap)..."
            )

            # Open viewer document
            viewer_doc = fitz.open(viewer_path)

            # Create source cluster info
            source_cluster = DrawingClusterInfo(
                rect=cluster_data.cluster_rect,
                drawing_count=cluster_data.drawing_count,
                page_num=cluster_data.page_num,
            )

            # Find matching cluster in viewer with offset-based search
            matcher = DrawingClusterMatcher()

            # Use absolute value of page offset as search range
            page_offset = self.state.page_offset
            search_range = abs(page_offset) if page_offset != 0 else 0

            match = matcher.find_best_match(
                viewer_doc, source_cluster, search_range_pages=search_range
            )

            if (
                match is None
                or match.total_score < DrawingClusterMatcher.MIN_MATCH_SCORE
            ):
                print("    ❌ MISS: No matching drawing cluster found")
                viewer_doc.close()
                self.state.transfer_stats["missed"] += 1
                return None

            print(
                f"         ✓ Found cluster match on page {match.cluster_info.page_num} "
                f"(score: {match.total_score:.2f})"
            )
            print(
                f"           Dimension: {match.dimension_score:.2f}, "
                f"Aspect: {match.aspect_score:.2f}, "
                f"Position: {match.position_score:.2f}, "
                f"Count: {match.count_score:.2f}"
            )

            # Reconstruct redaction
            transferer = DrawingClusterTransferer()
            new_rect = transferer.reconstruct_redaction(
                cluster_data, match.cluster_info
            )

            target_page_idx = match.cluster_info.page_num - 1  # Convert to 0-based
            target_page_num = match.cluster_info.page_num  # 1-based

            # Check overlap with existing redactions (50% threshold)
            new_box = PdfBox(
                x=new_rect.x0,
                y=new_rect.y0,
                w=new_rect.width,
                h=new_rect.height,
            )

            if self._overlaps_existing_redaction(new_box, target_page_idx, viewer_name):
                print(
                    f"         ⊘ SKIP: Overlaps existing at ({new_rect.x0:.1f}, {new_rect.y0:.1f})"
                )
                self.state.transfer_stats["missed"] += 1
                viewer_doc.close()
                return None

            # Create new redaction
            new_redaction = RedactionBox(
                id=str(uuid.uuid4()),
                x=new_rect.x0,
                y=new_rect.y0,
                w=new_rect.width,
                h=new_rect.height,
                page=target_page_num,
                selection_mode=SelectionMode.RECTANGLE,
                match=f"Drawing cluster (score: {match.total_score:.2f})",
                term="DRAWING_CLUSTER",
                batch_id=None,
            )

            print(
                f"         → Creating drawing cluster redaction at ({new_rect.x0:.1f}, {new_rect.y0:.1f})"
            )

            self.main.redaction_data.add_redaction_internal(
                new_redaction, target_page_idx, viewer_name
            )

            # Navigate to page where redaction was added
            self.main.viewer.navigate_to_page(viewer_name, target_page_num)

            viewer_doc.close()
            self.state.transfer_stats["matched"] += 1
            print("    ✓ SUCCESS: Drawing cluster redaction transferred")
            return target_page_num

        except Exception as e:
            print(f"    ❌ ERROR: Failed to transfer drawing cluster redaction: {e}")
            self.state.transfer_stats["missed"] += 1
            return None

    def _transfer_table_redaction(
        self,
        redaction: RedactionBox,
        redline_page_idx: int,
        viewer_path: str,
        viewer_name: str,
    ) -> int | None:
        """
        Transfer table-based redaction using table matching.

        Args:
            redaction: Redaction box from redline PDF
            redline_page_idx: Page index in redline PDF (0-based)
            viewer_path: Path to viewer PDF
            viewer_name: Viewer filename

        Returns:
            1-based page number if transferred, None if missed
        """
        from src.controllers.amendment.image_amendment import TableRedaction
        from src.controllers.amendment.match_and_place import (
            AdjacencyCellMatcher,
            RelativePositionReconstructor,
        )

        if not HAS_FITZ:
            self.state.transfer_stats["missed"] += 1
            return None

        try:
            # Parse stored table data
            if not redaction.match:
                self.state.transfer_stats["missed"] += 1
                return None

            table_data = TableRedaction.from_json(redaction.match)

            if table_data.center_cell:
                print(
                    f"    🔍 Searching for cell: '{table_data.center_cell.cell_text[:40]}...'"
                )
            else:
                print("    🔍 Searching for table redaction...")

            # Open viewer document
            viewer_doc = fitz.open(viewer_path)

            # Debug: Log cell reference offsets
            if table_data.center_cell:
                print(
                    f"    📍 Center cell offset: ({table_data.center_cell.offset_x:.2f}, {table_data.center_cell.offset_y:.2f})"
                )
                if table_data.up_cell:
                    print(
                        f"       Up cell offset: ({table_data.up_cell.offset_x:.2f}, {table_data.up_cell.offset_y:.2f})"
                    )
                if table_data.down_cell:
                    print(
                        f"       Down cell offset: ({table_data.down_cell.offset_x:.2f}, {table_data.down_cell.offset_y:.2f})"
                    )

            # Find best matching cell using adjacency scoring
            matcher = AdjacencyCellMatcher()
            match = matcher.find_best_matching_cell(
                viewer_doc, table_data, page_offset=self.state.page_offset
            )

            if not match:
                print("    ❌ MISS: No matching cell found")
                viewer_doc.close()
                self.state.transfer_stats["missed"] += 1
                return None

            print(f"         ✓ Found match on page {match.page_idx + 1}")
            print(
                f"           Score: {match.total_score:.2f} "
                f"(center={match.center_score:.2f}, "
                f"up={match.up_score:.2f}, down={match.down_score:.2f}, "
                f"left={match.left_score:.2f}, right={match.right_score:.2f})"
            )

            # Reconstruct position using multi-cell relativity
            reconstructor = RelativePositionReconstructor()
            dest_bbox = reconstructor.reconstruct_position(table_data, match)

            target_page_num = match.page_idx + 1  # 1-based from actual match page

            # Check overlap with existing redactions (50% threshold)
            new_box = PdfBox(
                x=dest_bbox[0],
                y=dest_bbox[1],
                w=dest_bbox[2] - dest_bbox[0],
                h=dest_bbox[3] - dest_bbox[1],
            )

            if self._overlaps_existing_redaction(new_box, match.page_idx, viewer_name):
                print(
                    f"         ⊘ SKIP: Overlaps existing at ({dest_bbox[0]:.1f}, {dest_bbox[1]:.1f})"
                )
                self.state.transfer_stats["missed"] += 1
                viewer_doc.close()
                return None

            # Calculate height of destination bbox
            dest_height = dest_bbox[3] - dest_bbox[1]

            # Use HIGHLIGHT for single-line text (same logic as text transfer)
            # Single line: ~12-15pt typical, multi-line: >20pt
            is_multiline = dest_height > 20
            selection_mode_to_use = (
                SelectionMode.RECTANGLE if is_multiline else SelectionMode.HIGHLIGHT
            )

            # Create new redaction
            cell_text = (
                table_data.center_cell.cell_text[:30]
                if table_data.center_cell
                else "unknown"
            )
            new_redaction = RedactionBox(
                id=str(uuid.uuid4()),
                x=dest_bbox[0],
                y=dest_bbox[1],
                w=dest_bbox[2] - dest_bbox[0],
                h=dest_bbox[3] - dest_bbox[1],
                page=target_page_num,
                selection_mode=selection_mode_to_use,
                match=f"Table cell adjacency match (score={match.total_score:.2f}, text: '{cell_text}...')",
                term="TABLE",
                batch_id=None,
            )

            print(
                f"         → Creating table redaction at ({dest_bbox[0]:.1f}, {dest_bbox[1]:.1f})"
            )

            self.main.redaction_data.add_redaction_internal(
                new_redaction, match.page_idx, viewer_name
            )

            # Navigate to page where redaction was added
            self.main.viewer.navigate_to_page(viewer_name, target_page_num)

            viewer_doc.close()
            self.state.transfer_stats["matched"] += 1
            print("    ✓ SUCCESS: Table redaction transferred")
            return target_page_num

        except Exception as e:
            print(f"    ❌ ERROR: Failed to transfer table redaction: {e}")
            self.state.transfer_stats["missed"] += 1
            return None

    def _overlaps_existing_redaction(
        self, new_box: PdfBox, page_idx: int, viewer_name: str
    ) -> bool:
        """Check if new box overlaps >50% with any existing redaction."""
        if not HAS_FITZ:
            return False

        existing_redactions = self.main.state.project.redactions.get(
            viewer_name, {}
        ).get(page_idx, [])

        if not existing_redactions:
            return False

        new_rect = fitz.Rect(
            new_box.x, new_box.y, new_box.x + new_box.w, new_box.y + new_box.h
        )
        new_area = new_rect.width * new_rect.height

        if new_area <= 0:
            return False

        for existing in existing_redactions:
            existing_rect = fitz.Rect(
                existing.x, existing.y, existing.x + existing.w, existing.y + existing.h
            )

            intersection = new_rect & existing_rect
            if intersection.is_empty:
                continue

            intersection_area = intersection.width * intersection.height
            overlap_pct = intersection_area / new_area

            if overlap_pct >= 0.5:
                return True

        return False

    def _load_destination_pdf(self, file_path: str) -> None:
        import os

        if not os.path.exists(file_path):
            self._show_error(f"File not found: {file_path}")
            return

        file_list = self.main.state.project.file_list
        if file_path not in file_list:
            file_list.append(file_path)
            self.main.state.project.file_list = file_list

            self.page.client_storage.set("selected_pdf_files", file_list)

            from src.ui.views import files_view

            files_view.render_file_list()

            self._show_success(f"Added to file list: {os.path.basename(file_path)}")
        else:
            self._show_success(f"Already in file list: {os.path.basename(file_path)}")

        self.main.viewer.navigate_to_page(file_path, 1)

        self._calculate_page_offset()

    def _calculate_page_offset(self) -> None:
        """Page offset = destination_pages - redline_pages.
        Used to determine search range for matching redactions."""
        redline_pages = self.state.redline_page_count
        destination_pages = self.main.state.viewer.total_pages

        if redline_pages > 0 and destination_pages > 0:
            self.state.page_offset = destination_pages - redline_pages
            print(
                f"Page offset calculated: {self.state.page_offset:+d} "
                f"(Redline: {redline_pages}, Destination: {destination_pages})"
            )
        else:
            self.state.page_offset = 0

    def search_images_on_page(self, page_number: int) -> None:
        """Search for all images on a specific page and print their coordinates.

        Args:
            page_number: 1-based page number
        """
        if not HAS_FITZ:
            print("❌ PyMuPDF not available")
            return

        if not self.state.redline_pdf_path:
            print("❌ No redline PDF loaded")
            return

        try:
            doc = fitz.open(self.state.redline_pdf_path)
            page_idx = page_number - 1  # Convert to 0-based

            if page_idx < 0 or page_idx >= len(doc):
                print(f"❌ Page {page_number} out of range (1-{len(doc)} available)")
                doc.close()
                return

            page = doc[page_idx]

            print(f"\n{'='*80}")
            print(f"DRAWING/IMAGE SEARCH: Page {page_number}")
            print(f"{'='*80}")

            # Check for regular images
            try:
                images = list(page.get_images())
                print(f"\n📷 Regular Images (get_images): {len(images)}")
                for i, img_info in enumerate(images, 1):
                    xref = img_info[0]  # Image xref
                    img_rect = page.get_image_bbox(xref)
                    print(f"  Image {i}: xref={xref} at {img_rect}")
            except Exception:
                print("\n📷 Regular Images: Failed to extract")

            # Check for drawings (vector graphics)
            drawings = page.get_drawings()
            print(f"\n✏️  Vector Drawings (get_drawings): {len(drawings)}")

            if len(drawings) == 0:
                print("  No drawings found")
            elif len(drawings) <= 20:
                # Show all if few
                for i, drawing in enumerate(drawings, 1):
                    rect = drawing["rect"]
                    print(
                        f"  Drawing {i}: ({rect.x0:.1f}, {rect.y0:.1f}, {rect.x1:.1f}, {rect.y1:.1f}) "
                        f"size: {rect.width:.1f}x{rect.height:.1f}"
                    )
            else:
                # Show sample + large ones
                print(f"  Total: {len(drawings)} drawings")
                print("\n  Large drawings (>100pt width or height):")
                large_drawings = [
                    d
                    for d in drawings
                    if d["rect"].width > 100 or d["rect"].height > 100
                ]
                for i, drawing in enumerate(large_drawings, 1):
                    rect = drawing["rect"]
                    print(
                        f"    [{i}] ({rect.x0:.1f}, {rect.y0:.1f}, {rect.x1:.1f}, {rect.y1:.1f}) "
                        f"size: {rect.width:.1f}x{rect.height:.1f}"
                    )

                # Show union of all drawings
                if drawings:
                    union_rect = None
                    for drawing in drawings:
                        rect = drawing["rect"]
                        if union_rect is None:
                            union_rect = rect
                        else:
                            union_rect |= rect
                    if union_rect is not None:
                        print(
                            f"\n  Union of ALL drawings: ({union_rect.x0:.1f}, {union_rect.y0:.1f}, "
                            f"{union_rect.x1:.1f}, {union_rect.y1:.1f})"
                        )
                        print(
                            f"    Size: {union_rect.width:.1f}x{union_rect.height:.1f} pts"
                        )

            # Check for redactions on this page to test clustering
            print("\n🔍 Testing Redaction-Based Clustering:")
            page_redactions = self.state.extracted_redactions.get(page_idx, [])

            if not page_redactions:
                print("  No redactions on this page to test clustering")
            else:
                print(f"  Found {len(page_redactions)} redaction(s) on page")
                for i, redaction in enumerate(page_redactions[:3], 1):  # Show first 3
                    redaction_rect = fitz.Rect(
                        redaction.x,
                        redaction.y,
                        redaction.x + redaction.w,
                        redaction.y + redaction.h,
                    )
                    print(
                        f"\n  Redaction {i}: ({redaction_rect.x0:.1f}, {redaction_rect.y0:.1f}, "
                        f"{redaction_rect.x1:.1f}, {redaction_rect.y1:.1f})"
                    )

                    # Find overlapping drawings
                    overlapping = [
                        d
                        for d in drawings
                        if (d["rect"] & redaction_rect).get_area() > 0
                    ]
                    print(f"    Directly overlapping drawings: {len(overlapping)}")

                    # Find nearby drawings (within 30pts)
                    expanded_rect = fitz.Rect(
                        redaction_rect.x0 - 30,
                        redaction_rect.y0 - 30,
                        redaction_rect.x1 + 30,
                        redaction_rect.y1 + 30,
                    )
                    nearby = [
                        d
                        for d in drawings
                        if (d["rect"] & expanded_rect).get_area() > 0
                    ]
                    print(f"    Nearby drawings (±30pts): {len(nearby)}")

                    # Cluster: union all nearby drawings
                    if nearby:
                        cluster_rect = None
                        for drawing in nearby:
                            rect = drawing["rect"]
                            if cluster_rect is None:
                                cluster_rect = rect
                            else:
                                cluster_rect |= rect
                        if cluster_rect is not None:
                            print(
                                f"    Clustered figure bounds: ({cluster_rect.x0:.1f}, {cluster_rect.y0:.1f}, "
                                f"{cluster_rect.x1:.1f}, {cluster_rect.y1:.1f})"
                            )
                            print(
                                f"    Clustered size: {cluster_rect.width:.1f}x{cluster_rect.height:.1f} pts"
                            )

            print(f"\n{'='*80}\n")
            doc.close()

        except Exception as e:
            print(f"❌ Failed to search drawings/images: {e}")
            import traceback

            traceback.print_exc()

    def draw_all_drawing_rects(self, page_number: int) -> None:
        """Draw rectangle redactions around each drawing on a page and navigate to it.

        Args:
            page_number: 1-based page number
        """
        if not HAS_FITZ:
            self._show_error("PyMuPDF not available")
            return

        # Get the viewer's current PDF
        if not self.main.state.viewer.file_path:
            self._show_error("No PDF loaded in viewer")
            return

        viewer_path = self.main.state.viewer.file_path
        viewer_name = self.main.state.viewer.file_name or "unknown.pdf"

        page_idx = page_number - 1  # Convert to 0-based

        try:
            doc = fitz.open(viewer_path)
            if page_idx < 0 or page_idx >= len(doc):
                self._show_error(f"Page {page_number} out of range")
                doc.close()
                return

            page = doc[page_idx]
            drawings = page.get_drawings()

            if not drawings:
                self._show_error(f"No drawings found on page {page_number}")
                doc.close()
                return

            print(f"\n{'='*80}")
            print(f"Drawing Rects for Page {page_number}")
            print(f"{'='*80}")
            print(f"Total drawings: {len(drawings)}\n")

            # Create a redaction box for each drawing
            from src.core.state.app_state import RedactionBox, SelectionMode
            import uuid

            for i, drawing in enumerate(drawings, 1):
                rect = drawing["rect"]
                print(
                    f"  [{i}] Drawing rect: ({rect.x0:.1f}, {rect.y0:.1f}, "
                    f"{rect.x1:.1f}, {rect.y1:.1f}) - {rect.width:.1f}x{rect.height:.1f}pts"
                )

                # Create redaction box
                redaction = RedactionBox(
                    id=str(uuid.uuid4()),
                    x=rect.x0,
                    y=rect.y0,
                    w=rect.width,
                    h=rect.height,
                    page=page_number,
                    selection_mode=SelectionMode.RECTANGLE,
                    match=f"Drawing {i}",
                    term="DEBUG_DRAWING",
                    batch_id=None,
                )

                # Add to viewer
                self.main.redaction_data.add_redaction_internal(
                    redaction, page_idx, viewer_name
                )

            doc.close()

            print(f"\n✓ Created {len(drawings)} drawing rects on page {page_number}")
            print(f"{'='*80}\n")

            # Navigate to the page
            self.main.viewer.navigate_to_page(viewer_path, page_number)

        except Exception as e:
            self._show_error(f"Failed to draw rects: {e}")
            import traceback

            traceback.print_exc()

    def print_redactions_from_page(self, page_number: int) -> None:
        """Print all redactions from a specific page (for debugging).

        Args:
            page_number: 1-based page number
        """
        page_idx = page_number - 1  # Convert to 0-based

        if not self.state.redline_pdf_path:
            self._show_error("No redline PDF loaded")
            return

        # Check if page has redactions
        redactions = self.state.extracted_redactions.get(page_idx, [])

        print(f"\n{'='*60}")
        print(f"REDACTIONS FROM PAGE {page_number}")
        print(f"{'='*60}")
        print(f"Redline PDF: {self.state.redline_pdf_name}")
        print(f"Total redactions on page: {len(redactions)}")
        print(f"{'-'*60}\n")

        if not redactions:
            print("No redactions found on this page.\n")
            self._show_warning(f"No redactions found on page {page_number}")
            return

        for i, redaction in enumerate(redactions, 1):
            print(f"Redaction #{i}:")
            print(f"  Position: x={redaction.x:.2f}, y={redaction.y:.2f}")
            print(f"  Size: w={redaction.w:.2f}, h={redaction.h:.2f}")

            # Use pre-extracted text if available (from combined lines)
            if redaction.match:
                text = redaction.match
                print(f"  Combined text (from lines): '{text}'")
            else:
                # Fall back to extracting from bounding box using standard method
                from src.core.domain.pdf_rendering import extract_text_under_rect

                box = PdfBox(x=redaction.x, y=redaction.y, w=redaction.w, h=redaction.h)
                text = extract_text_under_rect(
                    self.state.redline_pdf_path, page_idx, box
                )
                print(f"  Extracted text: '{text}'")

            print(f"  Text length: {len(text)} characters")
            print()

        print(f"{'='*60}\n")
        self._show_success(
            f"Printed {len(redactions)} redactions from page {page_number}"
        )

    def transfer_single_redaction(
        self, redline_page_idx: int, redaction: RedactionBox
    ) -> None:
        """Transfer a single redaction from the UI.

        Args:
            redline_page_idx: Page index in redline PDF (0-based)
            redaction: Redaction box to transfer
        """
        # Validate preconditions
        if not self.main.state.viewer.file_path:
            self._show_error("No document loaded in viewer.")
            return

        viewer_path = self.main.state.viewer.file_path
        viewer_name = self.main.state.viewer.file_name

        # Initialize transfer stats for single transfer
        self.state.transfer_stats = {"matched": 0, "missed": 0, "total": 1}

        print(f"\n{'='*60}")
        print(f"TRANSFER SINGLE: Page {redline_page_idx + 1}")
        print(f"{'='*60}")

        # Use Refactor transfer for all redaction types (NEW)
        transferred_page = self._transfer_single_redaction_refactor(
            redaction, redline_page_idx, viewer_path, viewer_name or ""
        )

        print(f"{'='*60}\n")

        if transferred_page is not None:
            print(f"Navigating to page {transferred_page}...")
            self.main.viewer.navigate_to_page(viewer_path, transferred_page)
            self._show_success(f"Transferred to page {transferred_page}")
        else:
            # Show error message
            self._show_warning("Failed to transfer redaction (see console for details)")

    def _find_text_in_viewer(
        self, text: str, viewer_path: str, original_page_idx: int
    ) -> list[tuple[int, list[PdfBox]]]:
        """Find text in viewer document and return line-level boxes.

        Args:
            text: Text to search for
            viewer_path: Path to viewer document
            original_page_idx: Original page index from redline (0-based)

        Returns:
            List of (page_idx, [line_boxes]) tuples - each match broken into lines
        """
        if not HAS_FITZ:
            return []

        matches = []
        doc = fitz.open(viewer_path)

        # Use redline page as search center
        center_page = original_page_idx  # 0-based

        # Use absolute value of page offset as search range
        page_offset = self.state.page_offset
        search_range = abs(page_offset) if page_offset != 0 else 0

        # Clamp search range to valid page bounds
        total_pages = len(doc)
        start_page = max(0, center_page - search_range)
        end_page = min(total_pages - 1, center_page + search_range)

        print(
            f"       Searching pages {start_page + 1}-{end_page + 1} "
            f"(redline page {center_page + 1}, offset {page_offset:+d}, range ±{search_range})"
        )
        print(f"       Target text: '{text[:100]}...' ({len(text)} chars)")

        # Try exact search first
        print("       🔍 Trying exact search...")
        for page_idx in range(start_page, end_page + 1):
            page = doc[page_idx]

            print(f"       Searching page {page_idx + 1}...")

            # Use PyMuPDF's search with case-insensitive and dehyphenation flags
            ignore_case = fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE
            dehyph = fitz.TEXT_DEHYPHENATE

            print(f"       Flags: ignore_case={ignore_case}, dehyphenate={dehyph}")

            # Search for exact text match
            rects = page.search_for(text, flags=ignore_case | dehyph)

            print(f"       search_for() returned {len(rects)} rect(s)")

            if rects:
                print(
                    f"       ✓ Page {page_idx + 1}: Found {len(rects)} exact match(es)"
                )

                # PyMuPDF returns multiple rects for multi-line text - combine them
                for rect_idx, rect in enumerate(rects, 1):
                    matched_text = page.get_text("text", clip=rect).strip()
                    print(
                        f"         Match {rect_idx}/{len(rects)}: '{matched_text[:50]}...' at ({rect.x0:.1f}, {rect.y0:.1f})"
                    )
                    print(
                        f"         Rect: x0={rect.x0:.1f}, y0={rect.y0:.1f}, x1={rect.x1:.1f}, y1={rect.y1:.1f}"
                    )
                    print(f"         Matched text length: {len(matched_text)} chars")

                    line_boxes = self._split_match_into_lines(page, rect)
                    print(f"         Split into {len(line_boxes)} line box(es)")
                    matches.append((page_idx, line_boxes))
            else:
                print(f"       ✗ No exact matches on page {page_idx + 1}")

        # If exact search found matches, return them
        if matches:
            print(f"       ✓ EXACT SEARCH SUCCESS: Found {len(matches)} match(es)")
            doc.close()
            return matches

        # No exact matches found - try fuzzy search
        print("       ✗ EXACT SEARCH FAILED: No exact matches found")
        print("       🔍 Trying fuzzy search (threshold=0.85)...")
        for page_idx in range(start_page, end_page + 1):
            print(f"       Fuzzy searching page {page_idx + 1}...")
            fuzzy_match = self._fuzzy_search_page(doc[page_idx], text, threshold=0.85)

            if fuzzy_match:
                matched_text = doc[page_idx].get_text("text", clip=fuzzy_match).strip()
                matched_text_normalized = " ".join(matched_text.split())

                print(
                    f"       ✓ Page {page_idx + 1}: Found fuzzy match '{matched_text_normalized[:50]}...' "
                    f"at ({fuzzy_match.x0:.1f}, {fuzzy_match.y0:.1f})"
                )
                print(
                    f"       Fuzzy match rect: x0={fuzzy_match.x0:.1f}, y0={fuzzy_match.y0:.1f}, x1={fuzzy_match.x1:.1f}, y1={fuzzy_match.y1:.1f}"
                )
                print(f"       Fuzzy matched text length: {len(matched_text)} chars")

                # Break down the match into individual line boxes
                line_boxes = self._split_match_into_lines(doc[page_idx], fuzzy_match)
                print(f"       Split into {len(line_boxes)} line box(es)")
                matches.append((page_idx, line_boxes))
            else:
                print(f"       ✗ No fuzzy match on page {page_idx + 1}")

        if matches:
            print(f"       ✓ FUZZY SEARCH SUCCESS: Found {len(matches)} match(es)")
        else:
            print("       ✗ FUZZY SEARCH FAILED: No matches found")

        doc.close()
        return matches

    def _fuzzy_search_page(
        self, page: fitz.Page, text: str, threshold: float
    ) -> fitz.Rect | None:
        """Fuzzy text matching using sliding window and SequenceMatcher."""
        from difflib import SequenceMatcher

        if not HAS_FITZ:
            return None

        words = page.get_text("words")

        if not words:
            return None

        best_ratio = 0.0
        best_rect = None

        target_lower = text.lower()
        target_word_count = len(target_lower.split())

        min_window = max(1, target_word_count - 5)
        max_window = min(len(words), target_word_count + 5)

        matcher = SequenceMatcher(None, target_lower, "")

        for window_size in range(min_window, max_window + 1):
            for i in range(len(words) - window_size + 1):
                combined_text = " ".join(
                    str(words[i + k][4]) for k in range(window_size)
                ).lower()

                len_diff = abs(len(combined_text) - len(target_lower))
                if len_diff > len(target_lower) * 0.3:
                    continue

                matcher.set_seq2(combined_text)
                ratio = matcher.ratio()

                if ratio > best_ratio:
                    best_ratio = ratio
                    min_x = min(float(words[i + k][0]) for k in range(window_size))
                    min_y = min(float(words[i + k][1]) for k in range(window_size))
                    max_x = max(float(words[i + k][2]) for k in range(window_size))
                    max_y = max(float(words[i + k][3]) for k in range(window_size))
                    best_rect = fitz.Rect(min_x, min_y, max_x, max_y)

                    if best_ratio >= 0.95:
                        print(
                            f"         🎯 Fuzzy match found with {best_ratio:.2%} similarity (threshold: {threshold:.2%})"
                        )
                        return best_rect

        if best_rect and best_ratio >= threshold:
            print(
                f"         🎯 Fuzzy match found with {best_ratio:.2%} similarity (threshold: {threshold:.2%})"
            )
            return best_rect

        return None

    def _split_match_into_lines(
        self, page: fitz.Page, match_rect: fitz.Rect
    ) -> list[PdfBox]:
        return [
            PdfBox(
                x=float(match_rect.x0),
                y=float(match_rect.y0),
                w=float(match_rect.width),
                h=float(match_rect.height),
            )
        ]
