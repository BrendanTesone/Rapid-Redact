from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from src.core.state.app_state import ResultCategory, SearchResult
from src.controllers.ai.ai_detection_controller import AIDetectionController
from src.controllers.ai.llm_client import DocumentContext
from src.core.state.ui_state import refs
from src.ui.views import base_results_view

if TYPE_CHECKING:
    from src.controllers.main_controller import MainController

_controller: MainController | None = None
_ai_controller: AIDetectionController | None = None


def register_ai_controller(ctrl: AIDetectionController) -> None:
    global _ai_controller
    _ai_controller = ctrl


def _passes_filters(item: SearchResult, filter_text: str) -> bool:
    if item.category != ResultCategory.PD_CHECKER:
        return False

    show_dismissed_ref = refs.get("chk_pd_checker_show_dismissed")
    show_dismissed = (
        show_dismissed_ref.current.value
        if show_dismissed_ref and show_dismissed_ref.current
        else False
    )
    if item.dismissed and not show_dismissed:
        return False

    status_filter_ref = refs.get("pd_checker_status_filter")
    status_filter = (
        status_filter_ref.current.value
        if status_filter_ref and status_filter_ref.current
        else "All"
    )

    if status_filter != "All":
        status_prefixes = {
            "Public": "✓ PUBLIC",
            "Not Found": "⚠ NOT FOUND",
            "Uncertain": "⚠ UNCERTAIN",
            "Not Checkable": "⊘ NOT CHECKABLE",
            "Not Checked": "○ Not Checked",
        }
        expected_prefix = status_prefixes.get(status_filter, "")
        if expected_prefix and expected_prefix not in item.term:
            return False

    return True


def navigate_to_redaction(
    file_name: str, file_path: str, page: int, highlight: str
) -> None:
    if not _controller:
        return
    _controller.viewer.navigate_to_page(file_path, page)


def render_pd_checker_list(filter_text: str = "") -> None:
    config = base_results_view.ResultsListConfig(
        listview_ref="pd_checker_list",
        term_predicate=lambda r: r.category == ResultCategory.PD_CHECKER,
        icon=ft.Icons.EDIT_NOTE,
        icon_color="#FF6F00",
        dismiss_checkbox_ref="chk_pd_checker_show_dismissed",
        passes_filters_fn=_passes_filters,
        navigate_fn=navigate_to_redaction,
        toggle_fn=base_results_view.toggle_result_redaction_simple,
    )
    base_results_view.render_results_list(config, filter_text)


def _make_verifier() -> object:
    # Public domain verification feature disabled (module removed)
    # TODO: Re-implement with LiteLLM or remove this tab
    raise NotImplementedError("Public domain verification feature is currently disabled")


def on_check_all_redactions(e: ft.ControlEvent) -> None:
    if not _controller or not _ai_controller:
        return

    status_ref = refs.get("pd_checker_status")
    progress_ref = refs.get("pd_checker_progress_bar")

    from src.core.domain.pdf_rendering import extract_text_under_rect
    from src.core.state.app_state import PdfBox

    items: list[tuple[str, str, str, str, str]] = []
    seen_batches: set[str] = set()

    for fname, pages in _controller.state.project.redactions.items():
        file_path = next(
            (
                path
                for path in _controller.state.project.file_list
                if path.endswith(fname)
            ),
            fname,
        )
        for page_idx, boxes in pages.items():
            for box in boxes:
                if box.w > 1000 or box.h > 1000:
                    continue

                identifier = box.batch_id if box.batch_id else box.id

                if box.batch_id and box.batch_id in seen_batches:
                    continue

                if box.batch_id:
                    seen_batches.add(box.batch_id)

                if box.match:
                    match_text = box.match
                else:
                    try:
                        pdf_box = PdfBox(x=box.x, y=box.y, w=box.w, h=box.h)
                        match_text = extract_text_under_rect(
                            file_path, page_idx, pdf_box
                        ).strip()
                    except Exception:
                        match_text = ""

                if match_text:
                    label = f"{fname}  p{page_idx + 1}"
                    items.append((match_text, match_text, label, fname, identifier))

    if not items:
        return

    if status_ref and status_ref.current:
        status_ref.current.value = f"Checking {len(items)} redaction(s)..."
        status_ref.current.visible = True
    if progress_ref and progress_ref.current:
        progress_ref.current.visible = True
        progress_ref.current.value = 0

    e.page.update()

    def _worker() -> None:
        import logging
        import fitz
        from src.public_domain.models import CheckResult
        from src.public_domain.verifier import PublicDomainVerifier

        verifier_obj = _make_verifier()
        verifier = (
            verifier_obj
            if isinstance(verifier_obj, PublicDomainVerifier)
            else PublicDomainVerifier(verifier_obj)  # type: ignore[arg-type]
        )

        # Extract compound aliases from every open PDF to filter against studied compounds
        compound_filter: list[str] | None = None
        if _ai_controller and _controller and _controller.state.project.file_list:
            seen_aliases: set[str] = set()
            aliases: list[str] = []
            for file_path in _controller.state.project.file_list:
                try:
                    with fitz.open(file_path) as doc:
                        toc = doc.get_toc()
                        total_pages = len(doc)
                        file_name = file_path.split("/")[-1].split("\\")[-1]

                        doc_context: DocumentContext | None = (
                            _ai_controller._extract_document_context(
                                doc, toc, total_pages, file_name
                            )
                        )
                    if doc_context:
                        compound_name = doc_context.get("compound_name", "")
                        if compound_name:
                            key = compound_name.lower()
                            if key not in seen_aliases:
                                seen_aliases.add(key)
                                aliases.append(compound_name)
                except Exception as ex:
                    logging.warning(
                        f"Failed to extract compound aliases from {file_path}: {ex}"
                    )
            if aliases:
                compound_filter = aliases
                logging.info(f"Using compound filter aliases: {compound_filter}")

        try:
            for i, (match_text, context, label, fname, identifier) in enumerate(
                items, 1
            ):
                if progress_ref and progress_ref.current:
                    progress_ref.current.value = i / len(items)
                if status_ref and status_ref.current:
                    status_ref.current.value = f"Checking {i}/{len(items)}: {label}"
                e.page.update()

                try:
                    result = verifier.check(
                        match_text, context, compound_filter=compound_filter
                    )

                    if isinstance(result, CheckResult):
                        for pages_dict in [
                            _controller.state.project.redactions.get(fname, {})
                        ]:
                            for boxes in pages_dict.values():
                                for box in boxes:
                                    box_id = box.batch_id if box.batch_id else box.id
                                    if box_id == identifier:
                                        box.pd_check_result = result
                except Exception as ex:
                    logging.error(f"PD check failed for {label}: {ex}")

            refresh_pd_checker_results()

        finally:
            if status_ref and status_ref.current:
                status_ref.current.visible = False
            if progress_ref and progress_ref.current:
                progress_ref.current.visible = False
            e.page.update()

    import threading

    threading.Thread(target=_worker, daemon=True).start()


def refresh_pd_checker_results() -> None:
    """Convert redactions to SearchResults. Batch redactions (same batch_id) are grouped into a single card."""
    if not _controller:
        return

    import fitz

    from src.core.domain.pdf_rendering import extract_text_under_rect
    from src.core.domain.pdf_search import preprocess_text
    from src.core.domain.pdf_text_position import extract_context_for_rect
    from src.core.state.app_state import PdfBox

    results: list[SearchResult] = []
    seen_batches: set[str] = set()

    for fname, pages in _controller.state.project.redactions.items():
        file_path = next(
            (
                path
                for path in _controller.state.project.file_list
                if path.endswith(fname)
            ),
            fname,
        )

        for page_idx, boxes in pages.items():
            for box in boxes:
                if box.batch_id and box.batch_id in seen_batches:
                    continue

                if box.batch_id:
                    seen_batches.add(box.batch_id)
                    batch_boxes = []
                    for p_idx, page_boxes in _controller.state.project.redactions[
                        fname
                    ].items():
                        for b in page_boxes:
                            if b.batch_id == box.batch_id:
                                batch_boxes.append((p_idx, b))
                else:
                    batch_boxes = [(page_idx, box)]

                pd_result = None
                for _, b in batch_boxes:
                    if b.pd_check_result:
                        pd_result = b.pd_check_result
                        break

                if pd_result:
                    verdict = pd_result.verdict.value.upper()
                    if verdict == "DISCLOSED":
                        pct = int(round(pd_result.confidence * 100))
                        status_prefix = f"✓ PUBLIC ({pct}%)"
                        n_sources = len(pd_result.evidence_urls)
                        if n_sources > 1:
                            status_prefix += f" · {n_sources} sources"
                    elif verdict == "NOT_FOUND":
                        status_prefix = "⚠ NOT FOUND"
                    elif verdict == "UNCERTAIN":
                        status_prefix = "⚠ UNCERTAIN"
                    else:
                        status_prefix = "⊘ NOT CHECKABLE"
                else:
                    status_prefix = "○ Not Checked"

                # Use sentence-bounded extractor for consistency with Matches tab
                context_parts = []
                redacted_text = ""
                source = "manual"

                try:
                    doc = fitz.open(file_path)
                except Exception:
                    doc = None

                try:
                    for p_idx, b in batch_boxes:
                        if b.match:
                            instance_text = b.match
                            source = b.term or "manual"
                        else:
                            try:
                                pdf_box = PdfBox(x=b.x, y=b.y, w=b.w, h=b.h)
                                instance_text = extract_text_under_rect(
                                    file_path, p_idx, pdf_box
                                ).strip()
                                if not instance_text:
                                    instance_text = (
                                        f"[Redaction at ({b.x:.0f}, {b.y:.0f})]"
                                    )
                            except Exception:
                                instance_text = f"[Redaction at ({b.x:.0f}, {b.y:.0f})]"

                        if not redacted_text:
                            redacted_text = instance_text

                        context = instance_text
                        if doc is not None and p_idx < len(doc):
                            try:
                                page = doc[p_idx]
                                processed_text = preprocess_text(
                                    str(page.get_text("text"))
                                )
                                rect = fitz.Rect(b.x, b.y, b.x + b.w, b.y + b.h)
                                context = extract_context_for_rect(
                                    page, rect, processed_text, context_size=80
                                )
                            except Exception:
                                context = instance_text
                        context_parts.append(context)
                finally:
                    if doc is not None:
                        doc.close()

                context_text = "   |   ".join(context_parts)

                result = SearchResult(
                    id=box.id,
                    file_name=fname,
                    file_path=file_path,
                    page=page_idx + 1,
                    term=f"{status_prefix} | {source}",
                    match=redacted_text,
                    context=context_text,
                    rects=[],
                    category=ResultCategory.PD_CHECKER,
                    redacted=True,
                    dismissed=False,
                    batch_id=box.batch_id or "",
                )
                results.append(result)

    disclosed = [r for r in results if "✓ PUBLIC" in r.term]
    not_found = [r for r in results if "⚠ NOT FOUND" in r.term]
    uncertain = [r for r in results if "⚠ UNCERTAIN" in r.term]
    not_checkable = [r for r in results if "⊘ NOT CHECKABLE" in r.term]
    not_checked = [r for r in results if "○ Not Checked" in r.term]

    results = disclosed + not_found + uncertain + not_checkable + not_checked

    _controller.state.search.all_search_results = [
        r
        for r in _controller.state.search.all_search_results
        if r.category != ResultCategory.PD_CHECKER
    ] + results

    render_pd_checker_list()


def build_view(controller: MainController) -> ft.Container:
    global _controller
    _controller = controller
    base_results_view.register_controller(controller)

    if "pd_checker_list" not in refs:
        refs["pd_checker_list"] = ft.Ref[ft.ListView]()
    if "chk_pd_checker_show_dismissed" not in refs:
        refs["chk_pd_checker_show_dismissed"] = ft.Ref[ft.Checkbox]()
    if "pd_checker_status_filter" not in refs:
        refs["pd_checker_status_filter"] = ft.Ref[ft.Dropdown]()
    if "pd_checker_status" not in refs:
        refs["pd_checker_status"] = ft.Ref[ft.Text]()
    if "pd_checker_progress_bar" not in refs:
        refs["pd_checker_progress_bar"] = ft.Ref[ft.ProgressBar]()

    return ft.Container(
        padding=5,
        content=ft.Column(
            [
                ft.ElevatedButton(
                    "FIND PUBLIC REDACTIONS",
                    on_click=on_check_all_redactions,
                    bgcolor="#009688",
                    color="white",
                    width=float("inf"),
                ),
                ft.Text(
                    ref=refs["pd_checker_status"],
                    visible=False,
                    size=12,
                    color="blue",
                ),
                ft.ProgressBar(
                    ref=refs["pd_checker_progress_bar"],
                    visible=False,
                    width=float("inf"),
                ),
                ft.Divider(height=1, color="#009688"),
                ft.Row(
                    [
                        ft.Text(
                            "Filter by status:", size=12, weight=ft.FontWeight.BOLD
                        ),
                        ft.Dropdown(
                            ref=refs["pd_checker_status_filter"],
                            value="All",
                            on_change=lambda _: render_pd_checker_list(),
                            width=200,
                            options=[
                                ft.dropdown.Option("All"),
                                ft.dropdown.Option("Public"),
                                ft.dropdown.Option("Not Found"),
                                ft.dropdown.Option("Uncertain"),
                                ft.dropdown.Option("Not Checkable"),
                                ft.dropdown.Option("Not Checked"),
                            ],
                        ),
                    ],
                    spacing=8,
                ),
                ft.Row(
                    [
                        ft.Checkbox(
                            ref=refs["chk_pd_checker_show_dismissed"],
                            label="Show dismissed",
                            value=False,
                            on_change=lambda _: render_pd_checker_list(),
                        ),
                    ],
                    spacing=8,
                ),
                ft.ListView(
                    ref=refs["pd_checker_list"],
                    expand=True,
                    spacing=5,
                    item_extent=85,
                ),
            ]
        ),
    )
