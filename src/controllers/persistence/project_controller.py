from __future__ import annotations

import logging
import os

import flet as ft

from src.core.domain.pdf_rendering import list_pdf_files
from src.core.domain.project_persistence import (
    save_project_to_file,
    load_project_from_file,
    ProjectData,
)
from src.core.state.app_state import SearchResult, DismissKey, SelectionMode
from src.core.state.ui_state import refs
from src.ui.views import files_view, viewer_view, bookmarks_view, matches_view

logger = logging.getLogger(__name__)


class ProjectPersistenceController:
    def __init__(self, main_controller: "MainController", page: ft.Page) -> None:  # type: ignore[name-defined]
        from src.controllers.main_controller import MainController

        self.main_controller: MainController = main_controller
        self.page: ft.Page = page

        self._project_save_picker: ft.FilePicker = ft.FilePicker(
            on_result=self._on_project_save_result
        )
        self._project_load_picker: ft.FilePicker = ft.FilePicker(
            on_result=self._on_project_load_result
        )
        self._pdf_save_picker: ft.FilePicker = ft.FilePicker(
            on_result=self._on_pdf_save_result
        )
        self._pleasereview_save_picker: ft.FilePicker = ft.FilePicker(
            on_result=self._on_pleasereview_save_result
        )

    def save_pdf(self, _: ft.ControlEvent) -> None:
        fname: str | None = self.main_controller.state.viewer.file_name
        file_path: str | None = self.main_controller.state.viewer.file_path
        if not fname or not file_path:
            self.page.open(ft.SnackBar(ft.Text("No PDF loaded."), bgcolor="grey"))
            return
        page_redactions_raw: object = self.main_controller.state.project.redactions.get(
            fname, {}
        )
        toc_redactions_raw: object = (
            self.main_controller.state.project.toc_redactions.get(fname, {})
        )
        if not page_redactions_raw and not toc_redactions_raw:
            self.page.open(
                ft.SnackBar(ft.Text("No redactions to save."), bgcolor="grey")
            )
            return

        default_filename = f"REDACTED_{fname}"
        self._pdf_save_picker.save_file(
            file_name=default_filename,
            allowed_extensions=["pdf"],
        )

    def _on_pdf_save_result(self, e: ft.FilePickerResultEvent) -> None:
        if not e.path:
            return

        output_path: str = str(e.path)
        if not output_path.lower().endswith(".pdf"):
            output_path += ".pdf"

        fname: str | None = self.main_controller.state.viewer.file_name
        file_path: str | None = self.main_controller.state.viewer.file_path

        if not fname or not file_path:
            return

        page_redactions_raw: object = self.main_controller.state.project.redactions.get(
            fname, {}
        )
        toc_redactions_raw: object = (
            self.main_controller.state.project.toc_redactions.get(fname, {})
        )

        import fitz

        with fitz.open(file_path) as doc:
            for p_idx, boxes in page_redactions_raw.items():  # type: ignore
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

                    quad = fitz.Quad(
                        pdf_rect.tl, pdf_rect.tr, pdf_rect.bl, pdf_rect.br
                    )
                    annot = page.add_redact_annot(quad)
                    annot.set_colors(stroke=[], fill=[])
                    annot.update()

                    doc.xref_set_key(annot.xref, "IC", ic_value)
                    doc.xref_set_key(annot.xref, "AP", "null")

            if toc_redactions_raw:
                toc = doc.get_toc(simple=True) or []
                new_toc = []
                for i, item in enumerate(toc):
                    lvl, title, page_num = item[0], item[1], item[2]
                    if i in toc_redactions_raw:  # type: ignore
                        title = toc_redactions_raw[i]  # type: ignore
                    new_toc.append([lvl, title, page_num])
                doc.set_toc(new_toc)

            doc.save(output_path, garbage=4, deflate=False)

        self.main_controller.state.project.batch_save_status[fname] = "saved"
        from src.ui.views import files_view

        files_view.render_file_list()
        self.page.open(
            ft.SnackBar(
                ft.Text(f"Saved: {os.path.basename(output_path)}"), bgcolor="green"
            )
        )

    def save_pdf_for_pleasereview(self, _: ft.ControlEvent) -> None:
        fname: str | None = self.main_controller.state.viewer.file_name
        file_path: str | None = self.main_controller.state.viewer.file_path

        if not fname or not file_path:
            self.page.open(ft.SnackBar(ft.Text("No PDF loaded."), bgcolor="grey"))
            return

        page_redactions: object = self.main_controller.state.project.redactions.get(
            fname, {}
        )
        if not page_redactions:
            self.page.open(
                ft.SnackBar(ft.Text("No redactions to export."), bgcolor="grey")
            )
            return

        default_filename = f"PLEASEREVIEW_COMMENTS_{fname}"
        self._pleasereview_save_picker.save_file(
            file_name=default_filename,
            allowed_extensions=["pdf"],
        )

    def _on_pleasereview_save_result(self, e: ft.FilePickerResultEvent) -> None:
        if not e.path:
            return

        output_path: str = str(e.path)
        if not output_path.lower().endswith(".pdf"):
            output_path += ".pdf"

        fname: str | None = self.main_controller.state.viewer.file_name
        file_path: str | None = self.main_controller.state.viewer.file_path

        if not fname or not file_path:
            return

        page_redactions_raw: object = self.main_controller.state.project.redactions.get(
            fname, {}
        )
        if not page_redactions_raw:
            return

        import datetime
        import uuid

        import fitz

        from src.core.state.app_state import RedactionBox

        if not isinstance(page_redactions_raw, dict):
            return

        batched_redactions: dict[int, dict[str, list[RedactionBox]]] = {}

        for page_idx, boxes in page_redactions_raw.items():
            if page_idx not in batched_redactions:
                batched_redactions[page_idx] = {}

            for box in boxes:
                batch_key: str = (
                    box.batch_id if box.batch_id else f"_unique_{box.id}"
                )

                if batch_key not in batched_redactions[page_idx]:
                    batched_redactions[page_idx][batch_key] = []

                batched_redactions[page_idx][batch_key].append(box)

        with fitz.open(file_path) as doc:
            for page in doc:
                annots = page.annots()
                if annots:
                    for annot in annots:
                        page.delete_annot(annot)

            for page_idx, batch_groups in batched_redactions.items():
                if page_idx >= len(doc):
                    continue

                page = doc[page_idx]

                for batch_key, boxes in batch_groups.items():
                    selection_mode = (
                        boxes[0].selection_mode
                        if boxes
                        else SelectionMode.HIGHLIGHT
                    )

                    now = datetime.datetime.now()
                    tz_offset = datetime.datetime.now().astimezone().strftime("%z")
                    tz_formatted = f"{tz_offset[:3]}'{tz_offset[3:]}'"
                    date_str = f"D:{now.strftime('%Y%m%d%H%M%S')}{tz_formatted}"

                    if selection_mode == SelectionMode.RECTANGLE:
                        for box in boxes:
                            pdf_rect = fitz.Rect(
                                box.x, box.y, box.x + box.w, box.y + box.h
                            )
                            rect_annot = page.add_rect_annot(pdf_rect)

                            rect_annot.set_info(
                                content="Please review this potential redaction",
                                title="Rapid Redact",
                                subject="Redaction Review",
                                creationDate=date_str,
                                modDate=date_str,
                            )

                            rect_annot.set_border(width=1.5, style="S")
                            rect_annot.set_name("Square")
                            rect_annot.set_opacity(0.5)
                            rect_annot.set_colors(
                                {"stroke": [1.0, 1.0, 0.0], "fill": [1.0, 1.0, 0.0]}
                            )
                            rect_annot.set_flags(132)
                            rect_annot.set_language("en-US")

                            xref = rect_annot.xref
                            unique_id = str(uuid.uuid4())
                            doc.xref_set_key(xref, "NM", f"({unique_id})")

                            rect_annot.update()

                    else:
                        quads = []
                        for box in boxes:
                            pdf_rect = fitz.Rect(
                                box.x, box.y, box.x + box.w, box.y + box.h
                            )
                            quad = fitz.Quad(
                                pdf_rect.tl, pdf_rect.tr, pdf_rect.bl, pdf_rect.br
                            )
                            quads.append(quad)

                        highlight = page.add_highlight_annot(quads)

                        highlight.set_info(
                            content="Please review this potential redaction",
                            title="Rapid Redact",
                            subject="Redaction Review",
                            creationDate=date_str,
                            modDate=date_str,
                        )

                        highlight.set_name("Highlight")
                        highlight.set_opacity(0.5)
                        highlight.set_colors(
                            {"stroke": [1.0, 1.0, 0.0], "fill": []}
                        )
                        highlight.set_flags(132)
                        highlight.set_language("en-US")
                        highlight.set_blendmode("Multiply")

                        xref = highlight.xref
                        unique_id = str(uuid.uuid4())
                        doc.xref_set_key(xref, "NM", f"({unique_id})")

                        highlight.update()

            doc.save(output_path, garbage=4, deflate=False)

        self.page.open(
            ft.SnackBar(
                ft.Text(f"Saved: {os.path.basename(output_path)}"), bgcolor="green"
            )
        )

        try:
            os.startfile(output_path)
        except Exception:
            pass

    def save_project(self, _: ft.ControlEvent | None = None) -> None:
        self._project_save_picker.save_file(
            file_name="redaction_project.json",
            allowed_extensions=["json"],
        )

    def _on_project_save_result(self, e: ft.FilePickerResultEvent) -> None:
        if not e.path:
            return
        path: str = str(e.path)
        if not path.lower().endswith(".json"):
            path += ".json"

        folder: str = str(self.page.client_storage.get("pdf_folder") or "")
        selected_files: list[str] = (
            self.page.client_storage.get("selected_pdf_files")
            or self.main_controller.state.project.file_list
            or []
        )
        dismissed_tuples: set[tuple[str, int, str, str]] = {
            (dk.file_name, dk.page, dk.match_text, dk.term)
            for dk in self.main_controller.state.search.dismissed_matches
        }
        save_project_to_file(
            file_path=path,
            redactions=self.main_controller.state.project.redactions,
            toc_redactions=self.main_controller.state.project.toc_redactions,
            dismissed_matches=dismissed_tuples,
            terms_list=self.main_controller.terms_list,
            selected_files=selected_files,
            folder=folder,
            search_results=self.main_controller.state.search.all_search_results,
            ai_detections=self.main_controller.state.ai_detection.all_detections,
            ai_library_path=self.main_controller.state.ai_detection.library_path,
            ai_document_summaries=self.main_controller.state.ai_detection.document_summaries,
            cci_auto_batch_ids=self.main_controller.state.search.cci_auto_batch_ids,
        )
        self.page.open(
            ft.SnackBar(
                ft.Text(f"Project saved: {os.path.basename(path)}"), bgcolor="green"
            )
        )

    def load_project(self, _: ft.ControlEvent | None = None) -> None:
        self._project_load_picker.pick_files(
            allowed_extensions=["json"],
            allow_multiple=False,
        )

    def _on_project_load_result(self, e: ft.FilePickerResultEvent) -> None:
        if not e.files:
            return
        try:
            path: str = str(e.files[0].path)
        except Exception:
            return

        data: ProjectData = load_project_from_file(path)

        self.main_controller.state.project.redactions.clear()
        self.main_controller.state.project.redactions.update(
            data.get("project_redactions", {})
        )

        self.main_controller.state.project.toc_redactions.clear()
        toc_data = data.get("project_toc_redactions")
        if toc_data:
            self.main_controller.state.project.toc_redactions.update(toc_data)

        dismissed_raw: object = data.get("dismissed_matches", set())
        dismissed_keys: set[DismissKey] = set()
        if isinstance(dismissed_raw, set):
            for item in dismissed_raw:
                if isinstance(item, (tuple, list)) and len(item) == 4:
                    dismissed_keys.add(
                        DismissKey(
                            file_name=str(item[0]),
                            page=int(item[1]),
                            match_text=str(item[2]),
                            term=str(item[3]),
                        )
                    )
        self.main_controller.state.search.dismissed_matches = dismissed_keys

        terms_raw: object = data.get("terms_list", [])
        from src.core.state.app_state import TermItem

        if isinstance(terms_raw, list):
            self.main_controller.terms_list = [
                TermItem(term=str(t["term"]), active=bool(t["active"]))
                for t in terms_raw
                if isinstance(t, dict) and "term" in t and "active" in t
            ]
        else:
            self.main_controller.terms_list = []
        terms_dicts = [
            {"term": t.term, "active": t.active}
            for t in self.main_controller.terms_list
        ]
        self.page.client_storage.set("terms_list", terms_dicts)
        self.main_controller.search_term.refresh_term_table()

        selected_files_raw: object = data.get("selected_files", [])
        selected_files: list[str] = (
            selected_files_raw if isinstance(selected_files_raw, list) else []
        )
        folder_raw: object = data.get("folder", "")
        folder: str = str(folder_raw) if folder_raw else ""
        valid_files: list[str] = [
            p for p in selected_files if isinstance(p, str) and os.path.exists(p)
        ]
        missing_files: list[str] = [
            p
            for p in selected_files
            if isinstance(p, str) and not os.path.exists(p)
        ]

        if valid_files:
            self.page.client_storage.set("selected_pdf_files", valid_files)
            self.page.client_storage.set("pdf_folder", folder)
            self.main_controller.state.project.file_list = valid_files
            if refs["folder_text"].current:
                label: str = f"{folder}  ({len(valid_files)} PDF(s) loaded)"
                if missing_files:
                    label += f"  [{len(missing_files)} file(s) missing]"
                refs["folder_text"].current.value = label
            files_view.render_file_list()
        elif folder:
            self.page.client_storage.set("pdf_folder", folder)
            self.main_controller.state.project.file_list = list_pdf_files(folder)
            if refs["folder_text"].current:
                refs["folder_text"].current.value = folder
            files_view.render_file_list()

        loaded_search_raw: object = data.get("search_results", [])
        loaded_search: list[SearchResult] = []
        if isinstance(loaded_search_raw, list):
            for r in loaded_search_raw:
                if isinstance(r, dict):
                    from src.core.state.app_state import ResultCategory
                    import uuid

                    term = str(r.get("term", ""))
                    category = ResultCategory(str(r.get("category", "matches")))

                    temp_result = SearchResult(
                        id=str(r.get("id", str(uuid.uuid4()))),
                        file_name=str(r.get("file_name", "")),
                        file_path=str(r.get("file_path", "")),
                        page=int(r.get("page", 0)),
                        match=str(r.get("match", "")),
                        term=term,
                        category=category,
                        context=str(r.get("context", "")),
                        batch_id=str(r.get("batch_id", "")),
                        redacted=False,
                        dismissed=False,
                    )
                    key: DismissKey = (
                        self.main_controller.search_results._dismiss_key(
                            temp_result
                        )
                    )
                    dismissed: bool = (
                        key in self.main_controller.state.search.dismissed_matches
                    )

                    bid: object = r.get("batch_id")
                    fname_raw: object = r.get("file_name", "")
                    fname_str: str = str(fname_raw) if fname_raw else ""
                    redacted: bool = False
                    if bid:
                        bid_str: str = str(bid)
                        for (
                            boxes
                        ) in self.main_controller.state.project.redactions.get(
                            fname_str, {}
                        ).values():
                            if any(b.batch_id == bid_str for b in boxes):
                                redacted = True
                                break

                    search_result = SearchResult(
                        id=temp_result.id,
                        file_name=temp_result.file_name,
                        file_path=temp_result.file_path,
                        page=temp_result.page,
                        match=temp_result.match,
                        term=temp_result.term,
                        category=temp_result.category,
                        context=temp_result.context,
                        batch_id=temp_result.batch_id,
                        redacted=redacted,
                        dismissed=dismissed,
                    )
                    loaded_search.append(search_result)

        self.main_controller.state.search.all_search_results = loaded_search

        from src.core.state.app_state import ResultCategory

        ai_detection_results = [
            r for r in loaded_search if r.category == ResultCategory.AI
        ]

        if ai_detection_results:
            from src.core.domain.ai_detection import find_text_coordinates

            count_ai_results = len(ai_detection_results)
            self.page.open(
                ft.SnackBar(
                    ft.Text(
                        f"Restoring coordinates for {count_ai_results} AI detections..."
                    ),
                    bgcolor="blue",
                )
            )

            by_file: dict[str, list[SearchResult]] = {}
            for result in ai_detection_results:
                if result.file_path not in by_file:
                    by_file[result.file_path] = []
                by_file[result.file_path].append(result)

            for file_path_str, file_results in by_file.items():
                if not os.path.exists(file_path_str):
                    logger.warning(
                        f"Skipping coordinate restoration for missing file: {file_path_str}"
                    )
                    continue

                try:
                    for result in file_results:
                        coords = find_text_coordinates(
                            pdf_path=file_path_str,
                            target_text=result.match,
                            page_hint=result.page,
                            context=result.context,
                        )

                        if coords:
                            result.rects = coords
                except Exception as e:
                    logger.warning(
                        f"Failed to restore coords for {file_path_str}: {e}"
                    )

            successful = sum(1 for r in ai_detection_results if r.rects)
            failed = len(ai_detection_results) - successful

            if failed > 0:
                self.page.open(
                    ft.SnackBar(
                        ft.Text(
                            f"Restored {successful}/{len(ai_detection_results)} AI detection coordinates. "
                            f"{failed} failed - text may have changed."
                        ),
                        bgcolor="orange",
                    )
                )
            else:
                self.page.open(
                    ft.SnackBar(
                        ft.Text(
                            f"Successfully restored all {successful} AI detection coordinates."
                        ),
                        bgcolor="green",
                    )
                )

        ai_detections_raw: object = data.get("ai_detections", [])
        if isinstance(ai_detections_raw, list):
            from src.core.state.ai_state import AIDetection

            self.main_controller.state.ai_detection.all_detections = [
                d for d in ai_detections_raw if isinstance(d, AIDetection)
            ]
        else:
            self.main_controller.state.ai_detection.all_detections = []

        if self.main_controller.state.ai_detection.all_detections:
            from src.core.domain.ai_detection import find_text_coordinates

            by_file_ai: dict[str, list[AIDetection]] = {}
            for detection in self.main_controller.state.ai_detection.all_detections:
                if detection.file_path not in by_file_ai:
                    by_file_ai[detection.file_path] = []
                by_file_ai[detection.file_path].append(detection)

            for file_path_str, detections in by_file_ai.items():
                if not os.path.exists(file_path_str):
                    logger.warning(
                        f"Skipping AI detection coordinate restoration for missing file: {file_path_str}"
                    )
                    continue

                try:
                    for detection in detections:
                        coords = find_text_coordinates(
                            pdf_path=file_path_str,
                            target_text=detection.text,
                            page_hint=detection.page,
                            context=detection.context,
                        )

                        if coords:
                            detection.rects = coords
                except Exception as e:
                    logger.warning(
                        f"Failed to restore AI detection coords for {file_path_str}: {e}"
                    )

        ai_library_path_raw: object = data.get("ai_library_path")
        self.main_controller.state.ai_detection.library_path = (
            str(ai_library_path_raw) if ai_library_path_raw else None
        )

        ai_doc_summaries_raw: object = data.get("ai_document_summaries", {})
        if isinstance(ai_doc_summaries_raw, dict):
            self.main_controller.state.ai_detection.document_summaries = dict(
                ai_doc_summaries_raw
            )
        else:
            self.main_controller.state.ai_detection.document_summaries = {}

        cci_batch_ids_raw: object = data.get("cci_auto_batch_ids", set())
        if isinstance(cci_batch_ids_raw, set):
            self.main_controller.state.search.cci_auto_batch_ids = cci_batch_ids_raw
        else:
            self.main_controller.state.search.cci_auto_batch_ids = set()

        from src.ui.views import ai_detection_view

        ai_detection_view.render_ai_detections_list()

        self.main_controller.state.project.undo_stack.clear()
        self.main_controller.state.project.redo_stack.clear()
        self.main_controller.redaction_data._update_undo_label()

        self.main_controller.search_results.refresh_results_term_filter_options()
        if self.main_controller.state.ui.current_tab == "bookmarks":
            bookmarks_view.render_bookmarks_list("")
        else:
            matches_view.render_text_results_list("")

        if valid_files:
            self.main_controller.viewer.navigate_to_page(valid_files[0], 1)

        count_redactions: int = sum(
            len(boxes)
            for pages in self.main_controller.state.project.redactions.values()
            for boxes in pages.values()
        )
        count_dismissed: int = len(
            self.main_controller.state.search.dismissed_matches
        )

        self.page.open(
            ft.SnackBar(
                ft.Text(
                    f"Project loaded: {os.path.basename(path)} — "
                    f"{count_redactions} redaction(s), "
                    f"{len(loaded_search)} search result(s), "
                    f"{count_dismissed} dismissed"
                ),
                bgcolor="green",
            )
        )

        if missing_files:
            names: str = ", ".join(os.path.basename(p) for p in missing_files[:5])
            suffix: str = (
                f" and {len(missing_files) - 5} more"
                if len(missing_files) > 5
                else ""
            )
            self.page.open(
                ft.SnackBar(
                    ft.Text(f"Warning: missing files: {names}{suffix}"),
                    bgcolor="orange",
                )
            )

    def save_folder(self, e: ft.FilePickerResultEvent) -> None:
        if not e.files:
            return
        selected_paths: list[str] = []
        for f in e.files:
            try:
                p: str = str(getattr(f, "path", "") or "")
            except Exception:
                p = ""
            if p and p.lower().endswith(".pdf") and os.path.exists(p):
                selected_paths.append(p)
        if not selected_paths:
            self.page.open(
                ft.SnackBar(ft.Text("No valid PDF files selected."), bgcolor="grey")
            )
            return

        existing_files: list[str] = self.main_controller.state.project.file_list
        existing_set: set[str] = set(existing_files)
        new_files: list[str] = [p for p in selected_paths if p not in existing_set]
        merged_list: list[str] = existing_files + new_files

        folder: str = os.path.dirname(selected_paths[0])
        self.page.client_storage.set("pdf_folder", folder)
        self.page.client_storage.set("selected_pdf_files", merged_list)
        self.main_controller.state.project.file_list = merged_list

        added_count: int = len(new_files)
        total_count: int = len(merged_list)
        if refs["folder_text"].current:
            if added_count < len(selected_paths):
                refs["folder_text"].current.value = (
                    f"{folder}  ({total_count} PDF(s), +{added_count} new)"
                )
            else:
                refs["folder_text"].current.value = (
                    f"{folder}  ({total_count} PDF(s) selected)"
                )
        if self.main_controller.state.ui.current_tab == "viewer":
            viewer_view.render_viewer_list("")
        else:
            files_view.render_file_list()
        self.page.update()

    def remove_file_from_list(self, file_path: str) -> None:
        file_list: list[str] = self.main_controller.state.project.file_list
        fname: str = os.path.basename(file_path)

        has_redactions: bool = False
        if fname in self.main_controller.state.project.redactions:
            has_redactions = any(
                boxes
                for boxes in self.main_controller.state.project.redactions[
                    fname
                ].values()
            )
        if (
            not has_redactions
            and fname in self.main_controller.state.project.toc_redactions
        ):
            has_redactions = bool(
                self.main_controller.state.project.toc_redactions[fname]
            )

        def do_remove() -> None:
            new_list: list[str] = [f for f in file_list if f != file_path]
            self.main_controller.state.project.file_list = new_list
            self.page.client_storage.set("selected_pdf_files", new_list)

            if fname in self.main_controller.state.project.redactions:
                del self.main_controller.state.project.redactions[fname]
            if fname in self.main_controller.state.project.toc_redactions:
                del self.main_controller.state.project.toc_redactions[fname]

            if self.main_controller.state.viewer.file_name == fname:
                self.main_controller.state.viewer.file_name = None
                self.main_controller.state.viewer.file_path = None
                self.main_controller.viewer._render_viewer()

            if new_list:
                folder: str = os.path.dirname(new_list[0])
                if refs["folder_text"].current:
                    refs["folder_text"].current.value = (
                        f"{folder}  ({len(new_list)} PDF(s) selected)"
                    )
            else:
                if refs["folder_text"].current:
                    refs["folder_text"].current.value = "No files selected"

            files_view.render_file_list()
            if self.main_controller.state.ui.current_tab == "viewer":
                viewer_view.render_viewer_list("")
            self.page.update()
            self.page.open(ft.SnackBar(ft.Text(f"Removed {fname}"), bgcolor="blue"))

        if has_redactions:
            def on_confirm(_: ft.ControlEvent) -> None:
                dlg.open = False
                self.page.update()
                do_remove()

            def on_cancel(_: ft.ControlEvent) -> None:
                dlg.open = False
                self.page.update()

            dlg: ft.AlertDialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Remove File?"),
                content=ft.Text(
                    f"{fname} has unsaved redactions. Are you sure you want to remove it?"
                ),
                actions=[
                    ft.TextButton("Remove", on_click=on_confirm),
                    ft.TextButton("Cancel", on_click=on_cancel),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            self.page.overlay.append(dlg)
            dlg.open = True
            self.page.update()
        else:
            do_remove()

    def _build_file_path_map(self) -> dict[str, str]:
        path_map: dict[str, str] = {}
        for fpath in self.main_controller.state.project.file_list:
            if isinstance(fpath, str) and os.path.exists(fpath):
                path_map[os.path.basename(fpath)] = fpath
        for search_result in self.main_controller.state.search.all_search_results:
            fname_result: str = search_result.file_name
            fpath_result: str = search_result.file_path
            if fname_result and fpath_result and os.path.exists(fpath_result):
                path_map.setdefault(fname_result, fpath_result)
        return path_map

    def register_pickers(self) -> None:
        self.page.overlay.append(self._project_save_picker)
        self.page.overlay.append(self._project_load_picker)
        self.page.overlay.append(self._pdf_save_picker)
        self.page.overlay.append(self._pleasereview_save_picker)
