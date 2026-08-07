"""AI detection controller for scan orchestration."""

import logging
import os
import threading
from typing import TypedDict, cast

import fitz

from src.controllers.ai.llm_client import (
    ChunkInfo,
    Detection,
    DocumentContext,
    LLMClient,
)
from src.core.state.ai_state import CCILibraryItem
from src.core.domain.ai_detection import find_text_coordinates
from src.core.domain.cci_library import load_cci_library
from src.core.domain.table_extraction import TableStructure
from src.core.state.ai_state import AIDetectionState
from src.core.state.app_state import AppState, SearchResult

logger = logging.getLogger(__name__)


def _optimal_chunk_worker_count(
    chunk_count: int, max_workers: int | None = None
) -> int:
    """
    HTTP I/O is the bottleneck, not CPU. HTTP session configured for
    50 concurrent connections, so we can exceed CPU count.
    Worker count: matches chunk_count (one worker per chunk).
    """
    if max_workers is not None:
        return max(1, min(chunk_count, max_workers))
    return max(1, chunk_count)


class PDFChunk(TypedDict):
    file_name: str
    file_path: str
    start_page: int
    end_page: int
    text: str
    section_title: str
    doc_context: "DocumentContext | None"


class AIDetectionController:
    """Orchestrates AI-powered CCI detection scan."""

    def __init__(
        self,
        state: AppState,
        ai_state: AIDetectionState,
        llm_client: LLMClient,
        main_controller: object | None = None,
    ):
        self.state = state
        self.ai_state = ai_state
        self.llm_client = llm_client
        self.main_controller = main_controller
        self._scan_thread: threading.Thread | None = None

    def run_ai_detection_scan(
        self, mode: str = "parallel", worker_count: int | None = None
    ) -> None:
        if self.ai_state.scan_running:
            logger.warning("Scan already running")
            return

        self.ai_state.scan_running = True
        self.ai_state.cancel_requested = False
        self.ai_state.all_detections.clear()

        self._scan_thread = threading.Thread(
            target=self._scan_worker, args=(mode, worker_count), daemon=True
        )
        self._scan_thread.start()
        logger.info(f"AI detection scan started (mode={mode}, workers={worker_count})")

    def run_ai_detection_current_page(self, file_path: str, page_number: int) -> None:
        if self.ai_state.scan_running:
            logger.warning("Scan already running")
            return

        self.ai_state.scan_running = True
        self.ai_state.cancel_requested = False
        self.ai_state.all_detections.clear()

        self._scan_thread = threading.Thread(
            target=self._scan_current_section_worker,
            args=(file_path, page_number),
            daemon=True,
        )
        self._scan_thread.start()
        logger.info(
            f"AI detection current section scan started: {file_path} page {page_number}"
        )

    def run_ai_detection_continuous(
        self, file_path: str, start_page: int, page: object, main_controller: object
    ) -> None:
        if self.ai_state.scan_running:
            logger.warning("Scan already running")
            return

        self.ai_state.scan_running = True
        self.ai_state.cancel_requested = False
        self.ai_state.all_detections.clear()

        self._scan_thread = threading.Thread(
            target=self._continuous_scan_worker,
            args=(file_path, start_page, page, main_controller),
            daemon=True,
        )
        self._scan_thread.start()
        logger.info(
            f"AI detection continuous scan started: {file_path} from page {start_page}"
        )

    def cancel_scan(self) -> None:
        if self.ai_state.scan_running:
            self.ai_state.cancel_requested = True
            logger.info("AI detection scan cancellation requested")

    def _scan_current_section_worker(self, file_path: str, page_number: int) -> None:
        try:
            self._update_progress(0.0, "Loading CCI library...")
            cci_library = load_cci_library(self.ai_state.library_path or "")

            if self.ai_state.cancel_requested:
                self._update_progress(1.0, "Scan cancelled")
                return

            from src.core.domain.toc_util import get_section_page_range

            self._update_progress(0.1, "Determining bookmark section...")

            file_name = os.path.basename(file_path)

            if not os.path.exists(file_path):
                self._update_progress(1.0, f"Error: File not found - {file_name}")
                return

            section_info = get_section_page_range(file_path, page_number)
            if not section_info:
                self._update_progress(1.0, "Error: Could not determine section range")
                return

            full_start_page, full_end_page, section_title = section_info
            logger.info(
                f"Section detection: page_number={page_number}, section='{section_title}', range={full_start_page}-{full_end_page}"
            )

            MAX_CHUNK_SIZE = 5
            section_size = full_end_page - full_start_page + 1

            if section_size > MAX_CHUNK_SIZE:
                chunk_start = full_start_page
                while chunk_start <= full_end_page:
                    chunk_end = min(chunk_start + MAX_CHUNK_SIZE - 1, full_end_page)
                    if chunk_start <= page_number <= chunk_end:
                        start_page = chunk_start
                        end_page = chunk_end
                        logger.info(
                            f"Section too large ({section_size} pages), using chunk: {start_page}-{end_page}"
                        )
                        break
                    chunk_start = chunk_end + 1
                else:
                    start_page = full_start_page
                    end_page = full_end_page
            else:
                start_page = full_start_page
                end_page = full_end_page

            self._update_progress(
                0.2,
                f"Extracting text (pages {start_page}-{end_page})...",
            )

            with fitz.open(file_path) as doc:
                total_pages = len(doc)
                toc: list[list[int | str]] = doc.get_toc(simple=True) or []
                doc_context = self._extract_document_context(
                    doc, toc, total_pages, file_name
                )

                section_text = ""
                for page_1based in range(start_page, end_page + 1):
                    page_0based = page_1based - 1
                    page = doc[page_0based]

                    from src.core.domain.table_extraction import (
                        extract_tables_from_page,
                    )

                    tables = extract_tables_from_page(page)

                    if not tables:
                        section_text += page.get_text("text") + "\n\n"
                    else:
                        section_text += self._extract_page_with_tables(page, tables)

                chunk: PDFChunk = PDFChunk(
                    file_name=file_name,
                    file_path=file_path,
                    start_page=start_page,
                    end_page=end_page,
                    text=section_text,
                    section_title=section_title,
                    doc_context=doc_context,
                )

            self._update_progress(
                0.4,
                f"Scanning section '{section_title}' (pages {start_page}-{end_page})...",
            )

            detections = self.llm_client.detect_cci(
                pdf_text=chunk["text"],
                cci_library=cci_library,
                chunk_info=cast(ChunkInfo, chunk),
            )

            for det in detections:
                det["file_name"] = file_name
                det["file_path"] = file_path

            self._update_progress(0.7, f"Processing {len(detections)} detections...")

            self.state.search.all_search_results = [
                r
                for r in self.state.search.all_search_results
                if not (
                    r.term.startswith("AI:")
                    and r.file_path == file_path
                    and start_page <= r.page <= end_page
                )
            ]

            if detections:
                self._convert_and_store_detections(detections)

            count = len(
                [
                    r
                    for r in self.state.search.all_search_results
                    if r.term.startswith("AI:")
                    and r.file_path == file_path
                    and start_page <= r.page <= end_page
                ]
            )
            section_desc = (
                f"'{section_title}'"
                if section_title
                else f"pages {start_page}-{end_page}"
            )
            completion_msg = (
                f"Section scan complete - {count} detection(s) found in {section_desc}"
            )
            self._update_progress(1.0, completion_msg)
            logger.info(
                f"AI detection section scan complete: {count} detections in {section_desc}"
            )

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self._update_progress(1.0, error_msg)
            logger.exception("AI detection current page scan failed")
        finally:
            self.ai_state.scan_running = False

            if self.main_controller and hasattr(self.main_controller, "viewer"):
                viewer_state = self.state.viewer
                if viewer_state.file_path:
                    viewer = getattr(self.main_controller, "viewer", None)
                    if viewer and hasattr(viewer, "navigate_to_page"):
                        viewer.navigate_to_page(
                            viewer_state.file_path, viewer_state.page_index + 1
                        )

    def _continuous_scan_worker(
        self, file_path: str, current_page: int, page: object, main_controller: object
    ) -> None:
        try:
            import fitz

            with fitz.open(file_path) as doc:
                toc: list[list[int | str]] = doc.get_toc(simple=True) or []
                total_pages = len(doc)

            level1_bookmarks = [
                (int(entry[2]), str(entry[1])) for entry in toc if int(entry[0]) == 1
            ]
            level1_bookmarks.sort(key=lambda x: x[0])

            if not level1_bookmarks:
                sections = [(1, total_pages, "")]
            else:
                sections = []
                for i, (bookmark_page, title) in enumerate(level1_bookmarks):
                    start_page = bookmark_page
                    if i + 1 < len(level1_bookmarks):
                        end_page = level1_bookmarks[i + 1][0] - 1
                    else:
                        end_page = total_pages
                    sections.append((start_page, end_page, title))

            if level1_bookmarks and level1_bookmarks[0][0] > 1:
                sections.insert(0, (1, level1_bookmarks[0][0] - 1, ""))

            start_section_idx = 0
            for idx, (sec_start, sec_end, sec_title) in enumerate(sections):
                if sec_start <= current_page <= sec_end:
                    start_section_idx = idx
                    logger.info(
                        f"Starting continuous scan from section {idx + 1}: '{sec_title}' (contains page {current_page})"
                    )
                    break

            total_sections = len(sections)
            sections_to_scan = sections[start_section_idx:]
            logger.info(
                f"Continuous scan: {len(sections_to_scan)} sections to scan (starting from section {start_section_idx + 1}/{total_sections})"
            )

            for section_idx, (start_page, end_page, section_title) in enumerate(
                sections_to_scan
            ):
                if self.ai_state.cancel_requested:
                    self._update_progress(1.0, "Scan cancelled")
                    return

                section_num = start_section_idx + section_idx + 1
                section_desc = (
                    f"'{section_title}'"
                    if section_title
                    else f"pages {start_page}-{end_page}"
                )

                logger.info(
                    f"Scanning section {section_num}/{total_sections}: {section_desc}"
                )

                overall_progress = section_idx / total_sections
                self._update_progress(
                    overall_progress,
                    f"Section {section_num}/{total_sections}: {section_desc}...",
                )

                mid_page = (start_page + end_page) // 2
                self._scan_section_sync(file_path, mid_page)

                from src.ui.views import ai_detection_view

                ai_detection_view.render_ai_detections_list()

                if hasattr(main_controller, "viewer") and hasattr(
                    main_controller, "state"
                ):
                    mc_state = getattr(main_controller, "state")
                    mc_viewer = getattr(main_controller, "viewer")
                    current_file = mc_state.viewer.file_path
                    current_page = mc_state.viewer.page_index + 1
                    if current_file == file_path:
                        mc_viewer.navigate_to_page(current_file, current_page)
                        mc_viewer._render_page_strip()

                if hasattr(page, "update"):
                    getattr(page, "update")()

            from src.core.state.app_state import ResultCategory

            ai_results = [
                r
                for r in self.state.search.all_search_results
                if r.category == ResultCategory.AI and not r.dismissed
            ]

            self._update_progress(
                1.0, f"Continuous scan complete - {len(ai_results)} total detections"
            )
            logger.info(
                f"Continuous scan complete: {len(ai_results)} detections across {total_sections} sections"
            )

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self._update_progress(1.0, error_msg)
            logger.exception("Continuous scan failed")
        finally:
            self.ai_state.scan_running = False

            # Navigate to current page to refresh overlays with AI detection highlights
            try:
                if main_controller and hasattr(main_controller, "viewer"):
                    viewer_state = self.state.viewer
                    if viewer_state.file_path:
                        viewer = getattr(main_controller, "viewer", None)
                        if viewer and hasattr(viewer, "navigate_to_page"):
                            viewer.navigate_to_page(
                                viewer_state.file_path, viewer_state.page_index + 1
                            )
            except Exception:
                pass

    def _scan_section_sync(self, file_path: str, page_number: int) -> None:
        try:
            import os

            import fitz

            from src.core.domain.cci_library import load_cci_library
            from src.core.domain.toc_util import get_section_page_range

            cci_library = load_cci_library(self.ai_state.library_path or "")

            if self.ai_state.cancel_requested:
                return

            file_name = os.path.basename(file_path)

            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_name}")
                return

            section_info = get_section_page_range(file_path, page_number)
            if not section_info:
                logger.error("Could not determine section range")
                return

            full_start_page, full_end_page, section_title = section_info

            MAX_CHUNK_SIZE = 5
            section_size = full_end_page - full_start_page + 1

            if section_size > MAX_CHUNK_SIZE:
                chunk_start = full_start_page
                while chunk_start <= full_end_page:
                    chunk_end = min(chunk_start + MAX_CHUNK_SIZE - 1, full_end_page)
                    if chunk_start <= page_number <= chunk_end:
                        start_page = chunk_start
                        end_page = chunk_end
                        break
                    chunk_start = chunk_end + 1
                else:
                    start_page = full_start_page
                    end_page = full_end_page
            else:
                start_page = full_start_page
                end_page = full_end_page

            with fitz.open(file_path) as doc:
                total_pages = len(doc)
                toc: list[list[int | str]] = doc.get_toc(simple=True) or []
                doc_context = self._extract_document_context(
                    doc, toc, total_pages, file_name
                )

                section_text = ""
                for page_1based in range(start_page, end_page + 1):
                    page_0based = page_1based - 1
                    page = doc[page_0based]

                    from src.core.domain.table_extraction import (
                        extract_tables_from_page,
                    )

                    tables = extract_tables_from_page(page)

                    if not tables:
                        section_text += page.get_text("text") + "\n\n"
                    else:
                        section_text += self._extract_page_with_tables(page, tables)

                chunk: PDFChunk = PDFChunk(
                    file_name=file_name,
                    file_path=file_path,
                    start_page=start_page,
                    end_page=end_page,
                    text=section_text,
                    section_title=section_title,
                    doc_context=doc_context,
                )

            detections = self.llm_client.detect_cci(
                pdf_text=chunk["text"],
                cci_library=cci_library,
                chunk_info=cast(ChunkInfo, chunk),
            )

            for det in detections:
                det["file_name"] = file_name
                det["file_path"] = file_path

            self.state.search.all_search_results = [
                r
                for r in self.state.search.all_search_results
                if not (
                    r.term.startswith("AI:")
                    and r.file_path == file_path
                    and start_page <= r.page <= end_page
                )
            ]

            if detections:
                self._convert_and_store_detections(detections)

        except Exception as e:
            logger.exception(f"Section scan failed: {e}")

    def _scan_worker(
        self, mode: str = "sequential", worker_count: int | None = None
    ) -> None:
        try:
            self._update_progress(0.0, "Loading CCI library...")
            cci_library = load_cci_library(self.ai_state.library_path or "")

            if self.ai_state.cancel_requested:
                self._update_progress(1.0, "Scan cancelled")
                return

            self._update_progress(0.05, "Extracting PDF text...")
            chunks, failed_files = self._extract_and_chunk_pdfs()

            if not chunks or self.ai_state.cancel_requested:
                status = (
                    "Scan cancelled"
                    if self.ai_state.cancel_requested
                    else "No PDFs to scan"
                )
                self._update_progress(1.0, status)
                return

            if mode == "sequential":
                all_raw_detections = self._scan_chunks_sequential(chunks, cci_library)
            else:
                all_raw_detections = self._scan_chunks_parallel(
                    chunks, cci_library, worker_count
                )

            logger.debug(
                f"All raw detections from scan: {len(all_raw_detections)} items"
            )

            self.state.search.all_search_results = [
                r
                for r in self.state.search.all_search_results
                if not r.term.startswith("AI:")
            ]

            if all_raw_detections:
                self._update_progress(
                    0.75,
                    f"Converting {len(all_raw_detections)} detections...",
                )
                self._convert_and_store_detections(all_raw_detections)
            else:
                logger.debug("No raw detections returned from LLM scan")

            count = len(
                [
                    r
                    for r in self.state.search.all_search_results
                    if r.term.startswith("AI:")
                ]
            )
            if failed_files:
                skipped = ", ".join(failed_files)
                completion_msg = (
                    f"Scan complete - {count} detections found "
                    f"({len(failed_files)} file(s) skipped: {skipped})"
                )
            else:
                completion_msg = f"Scan complete - {count} detections found"
            self._update_progress(1.0, completion_msg)
            logger.info(f"AI detection scan complete: {count} detections")

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self._update_progress(1.0, error_msg)
            logger.exception("AI detection scan failed")
        finally:
            self.ai_state.scan_running = False

            if self.main_controller and hasattr(self.main_controller, "viewer"):
                viewer_state = self.state.viewer
                if viewer_state.file_path:
                    viewer = getattr(self.main_controller, "viewer", None)
                    if viewer and hasattr(viewer, "navigate_to_page"):
                        viewer.navigate_to_page(
                            viewer_state.file_path, viewer_state.page_index + 1
                        )

    def _extract_and_chunk_pdfs(self) -> tuple[list[PDFChunk], list[str]]:
        """Extract text from PDFs and split into 5-page chunks for consistent processing time."""
        chunks: list[PDFChunk] = []
        failed: list[str] = []
        file_paths = self.state.project.file_list

        for file_path in file_paths:
            if not file_path.lower().endswith(".pdf"):
                continue

            file_name = os.path.basename(file_path)

            if not os.path.exists(file_path):
                logger.warning(f"File not found: {file_path}")
                failed.append(file_name)
                continue

            try:
                with fitz.open(file_path) as doc:
                    total_pages = len(doc)
                    toc: list[list[int | str]] = doc.get_toc(simple=True) or []
                    doc_context = self._extract_document_context(
                        doc, toc, total_pages, file_name
                    )

                    file_chunks: list[PDFChunk] = []
                    for start_0 in range(0, total_pages, 5):
                        end_0 = min(start_0 + 5, total_pages)
                        chunk_text = "".join(
                            doc[i].get_text("text") + "\n\n"
                            for i in range(start_0, end_0)
                        )
                        file_chunks.append(
                            PDFChunk(
                                file_name=file_name,
                                file_path=file_path,
                                start_page=start_0 + 1,
                                end_page=end_0,
                                text=chunk_text,
                                section_title="",
                                doc_context=doc_context,
                            )
                        )
                    chunks.extend(file_chunks)

            except Exception as e:
                logger.error(f"Failed to extract text from {file_name}: {e}")
                failed.append(file_name)

        return chunks, failed

    def _extract_page_with_tables(
        self, page: fitz.Page, tables: list["TableStructure"]
    ) -> str:
        """
        Extract page text including BOTH original table text AND formatted tables.
        Allows coordinate lookup on original text while LLM gets structured table understanding.
        """
        from src.core.domain.table_extraction import format_table_for_llm

        full_page_text: str = page.get_text("text")

        formatted_tables: list[str] = []
        for table in tables:
            formatted = format_table_for_llm(table)
            formatted_tables.append(formatted)

        if not formatted_tables:
            return str(full_page_text + "\n\n")

        page_text = str(full_page_text + "\n\n")
        page_text += "[STRUCTURED TABLE REPRESENTATIONS FOR REFERENCE]\n"
        page_text += "\n\n".join(formatted_tables)
        page_text += "\n\n"

        return page_text

    def _build_table_inventory(self, doc: fitz.Document, max_pages: int = 50) -> str:
        """Scans first 50 pages and returns table inventory: title, page, dimensions."""
        from src.core.domain.table_extraction import extract_tables_from_page

        inventory_lines: list[str] = []
        table_count = 0

        for page_num in range(min(len(doc), max_pages)):
            page = doc[page_num]
            tables = extract_tables_from_page(page)

            for table in tables:
                table_count += 1
                title = table.title or f"Untitled Table {table_count}"
                inventory_lines.append(
                    f"- {title} (Page {page_num + 1}, {table.col_count} cols x {table.row_count} rows)"
                )

        if not inventory_lines:
            return ""

        return (
            f"Document contains {table_count} tables:\n"
            + "\n".join(inventory_lines)
            + "\n"
        )

    def _extract_document_context(
        self,
        doc: fitz.Document,
        toc: list[list[int | str]],
        total_pages: int,
        file_name: str,
    ) -> "DocumentContext | None":
        """
        Extract document-level context before chunk processing.
        Identifies pre-content pages (title, TOC) and calls LLM once for doc_type and summary.
        """
        try:
            context_end_0 = 5
            if toc:
                l1 = [e for e in toc if int(e[0]) == 1]
                if l1:
                    first_content_page_1based = int(l1[0][2])
                    context_end_0 = min(first_content_page_1based - 1, total_pages, 8)
            context_end_0 = max(context_end_0, 1)

            title_pages = range(0, min(2, context_end_0))
            toc_pages = range(min(2, context_end_0), context_end_0)

            title_page_text = "".join(
                doc[i].get_text("text") for i in title_pages
            ).strip()
            toc_text = "".join(doc[i].get_text("text") for i in toc_pages).strip()

            if not title_page_text and not toc_text:
                logger.debug(
                    f"No extractable context text for {file_name} — skipping doc context"
                )
                return None

            toc_summary_lines: list[str] = []
            for entry in toc:
                level = int(entry[0])
                title = str(entry[1])
                page = int(entry[2])
                indent = "  " * (level - 1)
                toc_summary_lines.append(f"{indent}{title} (p.{page})")
            toc_summary = "\n".join(toc_summary_lines) if toc_summary_lines else ""

            table_inventory = self._build_table_inventory(doc)

            metadata = doc.metadata or {}
            pdf_title = (metadata.get("title") or "").strip()

            if file_name in self.ai_state.document_summaries:
                logger.info(f"Using cached document summary for {file_name}")
                cached_result = self.ai_state.document_summaries[file_name]
                doc_context = DocumentContext(
                    doc_title=cached_result.get("doc_title", pdf_title),
                    doc_type=cached_result.get("doc_type", ""),
                    toc_summary=toc_summary,
                    title_page_text=title_page_text,
                    toc_text=toc_text,
                    summary=cached_result.get("summary", ""),
                    table_inventory=table_inventory,
                )
                compound_name = cached_result.get("compound_name", "")
                if compound_name:
                    doc_context["compound_name"] = compound_name
                return doc_context

            result = self.llm_client.summarize_document(
                title_page_text=title_page_text,
                toc_text=toc_text,
                pdf_metadata_title=pdf_title,
            )

            if result is None:
                return None

            self.ai_state.document_summaries[file_name] = result
            logger.info(f"Cached document summary for {file_name}")

            doc_context = DocumentContext(
                doc_title=result.get("doc_title", pdf_title),
                doc_type=result.get("doc_type", ""),
                toc_summary=toc_summary,
                title_page_text=title_page_text,
                toc_text=toc_text,
                summary=result.get("summary", ""),
                table_inventory=table_inventory,
            )

            compound_name = result.get("compound_name", "")
            if compound_name:
                doc_context["compound_name"] = compound_name
                logger.info(f"Extracted compound name: {compound_name}")

            return doc_context

        except Exception as e:
            logger.warning(f"Failed to extract document context for {file_name}: {e}")
            return None

    def _scan_chunks_sequential(
        self, chunks: list[PDFChunk], cci_library: list[CCILibraryItem]
    ) -> list[Detection]:
        all_raw_detections: list[Detection] = []
        total_chunks = len(chunks)

        for i, chunk in enumerate(chunks):
            if self.ai_state.cancel_requested:
                self._update_progress(
                    1.0,
                    f"Scan cancelled - keeping {len(all_raw_detections)} partial results",
                )
                break

            progress = 0.05 + (0.7 * (i / total_chunks))
            section = (
                chunk["section_title"]
                or f"Pages {chunk['start_page']}-{chunk['end_page']}"
            )
            status = f"Scanning {chunk['file_name']}: {section} ({i+1}/{total_chunks})"
            self._update_progress(progress, status)

            try:
                detections = self.llm_client.detect_cci(
                    pdf_text=chunk["text"],
                    cci_library=cci_library,
                    chunk_info=cast(ChunkInfo, chunk),
                )

                for det in detections:
                    det["file_name"] = chunk["file_name"]
                    det["file_path"] = chunk["file_path"]

                all_raw_detections.extend(detections)

            except Exception as e:
                logger.error(
                    f"LLM API error for {chunk['file_name']} pages {chunk['start_page']}-{chunk['end_page']}: {e}"
                )
                continue

        return all_raw_detections

    def _scan_chunks_parallel(
        self,
        chunks: list[PDFChunk],
        cci_library: list[CCILibraryItem],
        worker_count: int | None = None,
    ) -> list[Detection]:
        """
        Thread-safe: LLMClient uses thread-safe token management and requests.Session.
        HTTP session pool supports 50 concurrent connections.
        """
        from concurrent.futures import Future, ThreadPoolExecutor, as_completed

        total_chunks = len(chunks)
        max_workers = _optimal_chunk_worker_count(total_chunks, worker_count)

        logger.info(
            f"Starting parallel scan: {total_chunks} chunks, {max_workers} workers"
        )

        all_raw_detections: list[Detection] = []
        completed_count = 0
        progress_lock = threading.Lock()

        def scan_single_chunk(chunk: PDFChunk) -> list[Detection]:
            try:
                detections = self.llm_client.detect_cci(
                    pdf_text=chunk["text"],
                    cci_library=cci_library,
                    chunk_info=cast(ChunkInfo, chunk),
                )

                for det in detections:
                    det["file_name"] = chunk["file_name"]
                    det["file_path"] = chunk["file_path"]

                return detections

            except Exception as e:
                logger.error(
                    f"LLM API error for {chunk['file_name']} "
                    f"pages {chunk['start_page']}-{chunk['end_page']}: {e}"
                )
                return []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_chunk: dict[Future[list[Detection]], PDFChunk] = {
                executor.submit(scan_single_chunk, chunk): chunk for chunk in chunks
            }

            for future in as_completed(future_to_chunk):
                if self.ai_state.cancel_requested:
                    for f in future_to_chunk:
                        f.cancel()
                    logger.info(
                        f"Parallel scan cancelled - keeping {len(all_raw_detections)} partial results"
                    )
                    break

                chunk = future_to_chunk[future]

                try:
                    detections = future.result()
                    all_raw_detections.extend(detections)

                except Exception as exc:
                    logger.warning(
                        f"Exception processing {chunk['file_name']} "
                        f"pages {chunk['start_page']}-{chunk['end_page']}: {exc}"
                    )

                with progress_lock:
                    completed_count += 1
                    progress = 0.05 + (0.7 * (completed_count / total_chunks))
                    status = (
                        f"Scanning in parallel ({max_workers} workers): "
                        f"{completed_count}/{total_chunks} chunks complete"
                    )
                    self._update_progress(progress, status)

        logger.info(
            f"Parallel scan complete: {len(all_raw_detections)} detections from {total_chunks} chunks"
        )
        return all_raw_detections

    def _convert_and_store_detections(self, raw_detections: list[Detection]) -> None:
        import hashlib
        import re
        import uuid
        from src.core.state.app_state import ResultCategory

        seen_rects: set[tuple[str, int, float, float, float, float]] = set()
        no_coord_seen: set[tuple[str, int, str]] = set()

        for detection in raw_detections:
            if self.ai_state.cancel_requested:
                break

            detected_text = detection["text"]
            normalized_text = re.sub(r"\s+", " ", detected_text).strip()

            normalized_text = re.sub(r"^\[ROW\]\s*", "", normalized_text)
            normalized_text = re.sub(r"^\[HEADER\]\s*", "", normalized_text)

            file_path = detection["file_path"]
            absolute_page = detection["page"]

            logger.debug(
                f"Looking up coordinates for: {normalized_text[:50]}... "
                f"in {detection['file_name']} page {absolute_page}"
            )

            rects = find_text_coordinates(
                file_path,
                normalized_text,
                absolute_page,
                detection.get("context", ""),
            )

            batch_id = hashlib.sha1(
                f"{file_path}:{absolute_page}:{normalized_text}".encode(),
                usedforsecurity=False,
            ).hexdigest()[:16]

            if rects:
                r0 = rects[0]
                rect_key = (
                    file_path,
                    absolute_page,
                    round(r0.x, 1),
                    round(r0.y, 1),
                    round(r0.x + r0.w, 1),
                    round(r0.y + r0.h, 1),
                )
                if rect_key in seen_rects:
                    continue
                seen_rects.add(rect_key)

                search_result = SearchResult(
                    id=str(uuid.uuid4()),
                    file_name=detection["file_name"],
                    file_path=file_path,
                    page=absolute_page,
                    match=normalized_text,
                    term=f"AI:{detection.get('category', 'Unknown')}",
                    category=ResultCategory.AI,
                    context=detection.get("context", ""),
                    batch_id=batch_id,
                    rects=rects,
                    redacted=False,
                    dismissed=False,
                )
                self.state.search.all_search_results.append(search_result)
            else:
                no_coord_key = (file_path, absolute_page, normalized_text)
                if no_coord_key in no_coord_seen:
                    continue
                no_coord_seen.add(no_coord_key)

                logger.warning(
                    f"Could not find coordinates for: {normalized_text[:50]}..."
                )
                search_result = SearchResult(
                    id=str(uuid.uuid4()),
                    file_name=detection["file_name"],
                    file_path=file_path,
                    page=absolute_page,
                    match=normalized_text,
                    term=f"AI:{detection.get('category', 'Unknown')}",
                    category=ResultCategory.AI,
                    context=detection.get("context", ""),
                    batch_id=batch_id,
                    rects=[],
                    redacted=False,
                    dismissed=False,
                )
                self.state.search.all_search_results.append(search_result)

        for result in self.state.search.all_search_results:
            if result.category == ResultCategory.AI:
                file_redactions = self.state.project.redactions.get(
                    result.file_name, {}
                )
                page_redactions = file_redactions.get(result.page - 1, [])

                for box in page_redactions:
                    if (
                        box.batch_id
                        and box.term == result.term
                        and box.match
                        and result.match
                        and box.match.lower().strip() == result.match.lower().strip()
                    ):
                        result.redacted = True
                        result.batch_id = box.batch_id
                        break

    def _update_progress(self, progress: float, status: str) -> None:
        self.ai_state.scan_progress = progress
        self.ai_state.scan_status = status
