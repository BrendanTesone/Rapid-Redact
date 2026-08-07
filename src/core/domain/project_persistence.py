"""Project file save/load operations.

Handles serialization and deserialization of project state to/from JSON files.
"""

import json
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from src.core.state.ai_state import AIDetection
    from src.core.state.app_state import (
        RedactionBox,
        TermItem,
        SearchResult,
    )


class DataclassEncoder(json.JSONEncoder):
    """JSON encoder that handles dataclass objects."""

    def default(self, obj: object) -> object:
        if hasattr(obj, "value"):
            return obj.value

        if is_dataclass(obj) and not isinstance(obj, type):
            result: dict[str, object] = {}
            for field_name, field_value in asdict(obj).items():
                if field_value is None:
                    continue
                # Runtime-only fields excluded from persistence
                if field_name in ("rects", "is_repeat_draft"):
                    continue
                result[field_name] = field_value
            return result
        return super().default(obj)


class ProjectData(TypedDict, total=False):
    """Type-safe structure for project file data."""

    project_redactions: dict[str, dict[int, list["RedactionBox"]]]
    project_toc_redactions: dict[str, dict[int, str]]
    dismissed_matches: set[tuple[str, int, str, str]]
    terms_list: list[dict[str, str | bool]]
    selected_files: list[str]
    folder: str
    search_results: list[dict[str, str | int]]
    ai_detections: list["AIDetection"]
    ai_library_path: str | None
    ai_document_summaries: dict[str, dict[str, str]]
    cci_auto_batch_ids: set[str]


def save_project_to_file(
    file_path: str,
    redactions: dict[str, dict[int, list["RedactionBox"]]],
    toc_redactions: dict[str, dict[int, str]],
    dismissed_matches: set[tuple[str, int, str, str]],
    terms_list: Sequence["TermItem"],
    selected_files: list[str],
    folder: str,
    search_results: Sequence["SearchResult"],
    ai_detections: Sequence["AIDetection"],
    ai_library_path: str | None,
    ai_document_summaries: dict[str, dict[str, str]],
    cci_auto_batch_ids: set[str],
) -> None:
    """Save project state to JSON file."""
    serialized_redactions: dict[str, dict[str, list["RedactionBox"]]] = {}
    for fname, pages in redactions.items():
        serialized_redactions[fname] = {}
        for page_idx, boxes in pages.items():
            serialized_redactions[fname][str(page_idx)] = boxes

    serialized_toc: dict[str, dict[str, str]] = {}
    for fname, entries in toc_redactions.items():
        serialized_toc[fname] = {str(k): v for k, v in entries.items()}

    data = {
        "project_redactions": serialized_redactions,
        "project_toc_redactions": serialized_toc,
        "dismissed_matches": list(dismissed_matches),
        "terms_list": terms_list,
        "selected_files": selected_files,
        "folder": folder,
        "search_results": search_results,
        "ai_detections": ai_detections,
        "ai_library_path": ai_library_path,
        "ai_document_summaries": ai_document_summaries,
        "cci_auto_batch_ids": list(cci_auto_batch_ids),
    }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, cls=DataclassEncoder)


def load_project_from_file(file_path: str) -> ProjectData:
    """Load project state from JSON file."""
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    from src.core.state.ai_state import AIDetection
    from src.core.state.app_state import PdfBox, RedactionBox, SelectionMode
    from src.public_domain.models import CheckResult, Verdict

    redactions_loaded = data.get("project_redactions", {})
    redactions_converted: dict[str, dict[int, list["RedactionBox"]]] = {}
    for fname, pages in redactions_loaded.items():
        redactions_converted[fname] = {}
        for page_key, boxes_data in pages.items():
            page_idx = int(page_key)
            boxes: list[RedactionBox] = []
            for box_data in boxes_data:
                if not isinstance(box_data, dict):
                    continue

                pd_check_result = None
                if "pd_check_result" in box_data:
                    pd_data = box_data["pd_check_result"]
                    if isinstance(pd_data, dict):
                        pd_check_result = CheckResult(
                            verdict=Verdict(pd_data.get("verdict", "not_found")),
                            claim=pd_data.get("claim", ""),
                            confidence=pd_data.get("confidence", 0.0),
                            source_name=pd_data.get("source_name", ""),
                            url=pd_data.get("url", ""),
                            quote=pd_data.get("quote", ""),
                            detail=pd_data.get("detail", ""),
                        )

                # Migration: old "redact" enum value -> "highlight"
                box = RedactionBox(
                    id=box_data.get("id", ""),
                    x=float(box_data.get("x", 0.0)),
                    y=float(box_data.get("y", 0.0)),
                    w=float(box_data.get("w", 0.0)),
                    h=float(box_data.get("h", 0.0)),
                    page=int(box_data.get("page", page_idx)),
                    selection_mode=SelectionMode(
                        "highlight"
                        if box_data.get("selection_mode", "highlight") == "redact"
                        else box_data.get("selection_mode", "highlight")
                    ),
                    match=box_data.get("match"),
                    term=box_data.get("term"),
                    batch_id=box_data.get("batch_id"),
                    pd_check_result=pd_check_result,
                    repeat_pages=box_data.get("repeat_pages", []),
                    section_title=box_data.get("section_title"),
                )
                boxes.append(box)
            redactions_converted[fname][page_idx] = boxes

    toc_loaded = data.get("project_toc_redactions", {})
    toc_converted: dict[str, dict[int, str]] = {}
    for fname, entries in toc_loaded.items():
        toc_converted[fname] = {int(k): v for k, v in entries.items()}

    dismissed_list = data.get("dismissed_matches", [])
    dismissed_set: set[tuple[str, int, str, str]] = set()
    for item in dismissed_list:
        if isinstance(item, (list, tuple)) and len(item) == 4:
            dismissed_set.add((str(item[0]), int(item[1]), str(item[2]), str(item[3])))

    ai_detections_loaded = data.get("ai_detections", [])
    ai_detections_converted: list[AIDetection] = []
    for detection_data in ai_detections_loaded:
        if not isinstance(detection_data, dict):
            continue

        rects_data = detection_data.get("rects", [])
        rects: list[PdfBox] = []
        for rect_data in rects_data:
            if isinstance(rect_data, dict):
                rects.append(
                    PdfBox(
                        x=float(rect_data.get("x", 0.0)),
                        y=float(rect_data.get("y", 0.0)),
                        w=float(rect_data.get("w", 0.0)),
                        h=float(rect_data.get("h", 0.0)),
                    )
                )

        detection = AIDetection(
            text=str(detection_data.get("text", "")),
            page=int(detection_data.get("page", 0)),
            file_name=str(detection_data.get("file_name", "")),
            file_path=str(detection_data.get("file_path", "")),
            confidence=str(detection_data.get("confidence", "low")),
            category=str(detection_data.get("category", "")),
            justification=str(detection_data.get("justification", "")),
            context=str(detection_data.get("context", "")),
            rects=rects,
            redacted=bool(detection_data.get("redacted", False)),
            dismissed=bool(detection_data.get("dismissed", False)),
            batch_id=str(detection_data.get("batch_id", "")),
        )
        ai_detections_converted.append(detection)

    cci_auto_batch_ids_list = data.get("cci_auto_batch_ids", [])
    cci_auto_batch_ids_set: set[str] = (
        set(cci_auto_batch_ids_list)
        if isinstance(cci_auto_batch_ids_list, list)
        else set()
    )

    return {
        "project_redactions": redactions_converted,
        "project_toc_redactions": toc_converted,
        "dismissed_matches": dismissed_set,
        "terms_list": data.get("terms_list", []),
        "selected_files": data.get("selected_files", []),
        "folder": data.get("folder", ""),
        "search_results": data.get("search_results", []),
        "ai_detections": ai_detections_converted,
        "ai_library_path": data.get("ai_library_path"),
        "ai_document_summaries": data.get("ai_document_summaries", {}),
        "cci_auto_batch_ids": cci_auto_batch_ids_set,
    }
