"""Typed application state using dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.state.ai_state import AIDetectionState
    from src.core.state.amendment.amendment_state import AmendmentState
    from src.public_domain.models import CheckResult


class ResultCategory(str, Enum):
    MATCHES = "matches"
    DOSAGE = "dosage"
    AI = "ai"
    GAP = "gap"
    PD_CHECKER = "pd_checker"


class SelectionMode(str, Enum):
    RECTANGLE = "rectangle"
    HIGHLIGHT = "highlight"


@dataclass(slots=True, frozen=True)
class PdfBox:
    """PDF coordinate box (immutable)."""

    x: float
    y: float
    w: float
    h: float


@dataclass(slots=True)
class RedactionBox:
    """A single redaction box on a PDF page."""

    id: str
    x: float
    y: float
    w: float
    h: float
    page: int
    selection_mode: SelectionMode = SelectionMode.HIGHLIGHT
    match: str | None = None
    term: str | None = None
    batch_id: str | None = None
    context: str | None = None  # Surrounding context for AI matching (±50 chars)
    pd_check_result: CheckResult | None = None
    is_repeat_draft: bool = False  # True when awaiting repeat confirmation dialog
    repeat_pages: list[int] = field(default_factory=list)
    section_title: str | None = None


@dataclass(slots=True)
class TableRedactionBox(RedactionBox):
    """RedactionBox with table-specific metadata for sophisticated matching."""

    adjacency_graph: dict[tuple[int, int], dict[str, str | None]] = field(
        default_factory=dict
    )
    headers: list[str] = field(default_factory=list)
    title: str | None = None
    row_count: int = 0
    col_count: int = 0
    table_bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


@dataclass(slots=True)
class TableMatchScore:
    table_idx: int
    adjacency_score: float
    structure_score: float
    header_score: float
    title_score: float
    position_score: float
    total_score: float
    table_bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


@dataclass(slots=True)
class SearchResult:
    """A single search result match."""

    id: str
    file_name: str
    file_path: str
    page: int
    match: str
    term: str
    category: ResultCategory
    context: str
    batch_id: str
    redacted: bool = False
    dismissed: bool = False
    rects: list[PdfBox] = field(default_factory=list)


class HighlightMode(Enum):
    """Determines which search results are shown as yellow overlays when rendering PDF pages."""

    NONE = "none"
    SINGLE_TERM = "single"
    ALL_TERMS = "all"


@dataclass(frozen=True)
class HighlightFilter:
    """Configuration for filtering which search results to highlight.

    Used by should_highlight_result() pure function in rendering_controller.
    """

    current_file: str
    current_page: int
    mode: HighlightMode
    term: str = ""
    category_filter: ResultCategory | None = None


@dataclass(slots=True)
class BookmarkItem:
    level: int
    title: str
    page: int
    end_page: int
    file_path: str
    term: str
    original_index: int | None = None
    file_name: str | None = None
    redacted_term_toc: bool = False
    redacted_term_pages: bool = False
    term_pages_batch_id: str | None = None
    title_redacted: bool = False


# ConsistencyGap removed - consistency gaps are now stored as SearchResult objects
# with category=ResultCategory.GAP, eliminating unnecessary wrapper and deduplication bugs


@dataclass(slots=True)
class UndoActionAddBox:
    action: str
    file_name: str
    page_idx: int
    box: RedactionBox


@dataclass(slots=True)
class UndoActionRemoveBox:
    action: str
    file_name: str
    page_idx: int
    box: RedactionBox


@dataclass(slots=True)
class TermItem:
    term: str
    active: bool


@dataclass(frozen=True, slots=True)
class DismissKey:
    file_name: str
    page: int
    match_text: str
    term: str


@dataclass(slots=True)
class UndoEntry:
    file_name: str
    page_idx: int
    box: RedactionBox


@dataclass(slots=True)
class UndoActionRemoveBoxes:
    action: str
    entries: list[UndoEntry]


@dataclass(slots=True)
class UndoActionAddBatch:
    action: str
    file_name: str
    page_idx: int
    boxes: list[RedactionBox]


@dataclass(slots=True)
class UndoActionEditBox:
    action: str
    file_name: str
    page_idx: int
    old_box: RedactionBox
    new_box: RedactionBox


@dataclass(slots=True, frozen=True)
class TextSpan:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(slots=True, frozen=True)
class TextLine:
    spans: list[TextSpan]


@dataclass(slots=True)
class TextStructure:
    lines: list[TextLine]


@dataclass(slots=True)
class ViewerState:
    """PDF viewer and navigation state.

    Default panel widths are defined here for initialization.
    These can be overridden by AppConfig.ui values at runtime.
    """

    file_path: str | None = None
    file_name: str | None = None
    page_index: int = 0
    total_pages: int = 0
    zoom: float = 1.0
    scale_factors: dict[int, float] = field(default_factory=dict)
    base_width: int = 800
    left_panel_width: int = 320
    middle_panel_width: int = 414
    bookmarks_panel_visible: bool = False


@dataclass(slots=True)
class SearchState:
    current_term: str = ""
    active_search_terms: list[str] = field(default_factory=list)
    results_term_filter: str = ""
    all_search_results: list[SearchResult] = field(default_factory=list)
    dismissed_matches: set[DismissKey] = field(default_factory=set)
    show_dismissed: bool = False
    search_running: bool = False
    # CCI dosing feature flags (always enabled)
    show_cci_dosing_results: bool = True
    smart_dosing_filter_enabled: bool = True
    cci_auto_batch_ids: set[str] = field(default_factory=set)


@dataclass(slots=True)
class RedactionSelectionState:
    active: bool = False
    start_point: tuple[float, float] | None = None
    end_point: tuple[float, float] | None = None
    page_index: int | None = None
    text_cache: dict[str, TextStructure] = field(default_factory=dict)
    char_cache: dict[str, list[tuple[float, float, float, float, str]]] = field(
        default_factory=dict
    )


@dataclass(slots=True)
class RedactionState:
    drawing_mode: str = "normal"
    selection_mode: str = "highlight_redact"
    selected_annotation_ids: set[str] = field(default_factory=set)
    draft_box_id: str | None = None
    temp_target_box: RedactionBox | None = None


@dataclass(slots=True)
class UIState:
    current_tab: str = "viewer"
    last_results_tab: str = "matches"
    tab_panel_collapsed: bool = False
    expanded_files: set[str] = field(default_factory=set)


UndoAction = (
    UndoActionAddBox
    | UndoActionRemoveBox
    | UndoActionRemoveBoxes
    | UndoActionAddBatch
    | UndoActionEditBox
)


@dataclass(slots=True)
class ProjectState:
    undo_stack: list[UndoAction] = field(default_factory=list)
    redo_stack: list[UndoAction] = field(default_factory=list)
    file_list: list[str] = field(default_factory=list)
    current_file_bookmarks: list[BookmarkItem] = field(default_factory=list)
    batch_save_status: dict[str, str] = field(default_factory=dict)
    redactions: dict[str, dict[int, list[RedactionBox]]] = field(default_factory=dict)
    toc_redactions: dict[str, dict[int, str]] = field(default_factory=dict)


@dataclass(slots=True)
class ConsistencyState:
    consistency_running: bool = False
    consistency_scan_status: str = "idle"
    consistency_last_scan: str = ""


@dataclass(slots=True)
class AppState:
    """Root application state containing all domain-specific state."""

    viewer: ViewerState = field(default_factory=ViewerState)
    search: SearchState = field(default_factory=SearchState)
    redaction_selection: RedactionSelectionState = field(
        default_factory=RedactionSelectionState
    )
    redaction: RedactionState = field(default_factory=RedactionState)
    ui: UIState = field(default_factory=UIState)
    project: ProjectState = field(default_factory=ProjectState)
    consistency: ConsistencyState = field(default_factory=ConsistencyState)
    ai_detection: AIDetectionState = field(init=False)
    amendment: AmendmentState = field(init=False)

    def __post_init__(self) -> None:
        from src.core.state.ai_state import AIDetectionState
        from src.core.state.amendment.amendment_state import AmendmentState

        object.__setattr__(self, "ai_detection", AIDetectionState())
        object.__setattr__(self, "amendment", AmendmentState())
