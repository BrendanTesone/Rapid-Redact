"""
Text selection state management.

Inspired by browser DOM Selection API: start (anchor), focus (cursor),
and normalized range (always in reading order).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SelectionPoint:
    """A point in text (character-level), combining PDF coordinates and character index."""

    x: float
    y: float
    snapped_char_idx: int | None = None
    line_index: int | None = None

    def __eq__(self, other: object) -> bool:
        """Coordinate-based equality. snapped_char_idx may differ during drag."""
        if not isinstance(other, SelectionPoint):
            return False
        return abs(self.x - other.x) < 1.0 and abs(self.y - other.y) < 1.0


@dataclass
class SelectionSpan:
    """A contiguous block of selected text with its bounding box."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    line_index: int
    span_index: int = 0


@dataclass
class SelectionRange:
    """Normalized selection range (start always before end in reading order)."""

    start: SelectionPoint
    end: SelectionPoint
    spans: list[SelectionSpan] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "".join(span.text for span in self.spans)

    @property
    def is_empty(self) -> bool:
        return len(self.spans) == 0


@dataclass
class TextSelection:
    """Document-level text selection state.

    Selection states:
    - collapsed: start == focus (cursor only)
    - range: start != focus (text selected)

    Range is always normalized to reading order regardless of drag direction.
    """

    start: SelectionPoint | None = None
    focus: SelectionPoint | None = None
    page_index: int | None = None
    file_path: str | None = None
    _cached_range: SelectionRange | None = field(default=None, repr=False)

    @property
    def is_active(self) -> bool:
        return self.start is not None

    @property
    def is_collapsed(self) -> bool:
        if not self.is_active:
            return True
        if self.focus is None:
            return True
        return self.start == self.focus

    @property
    def range(self) -> SelectionRange | None:
        """Normalized range (start→end in reading order). Cached until start/focus changes."""
        if self.is_collapsed:
            return None
        return self._cached_range

    def set_start_and_page_index(self, point: SelectionPoint, page_index: int) -> None:
        self.start = point
        self.page_index = page_index
        self._cached_range = None

    def set_focus(self, point: SelectionPoint) -> None:
        if not self.is_active:
            return
        self.focus = point
        self._cached_range = None

    def set_range(self, range: SelectionRange) -> None:
        """Called by selection logic after computing text spans within start/focus region."""
        self._cached_range = range

    def collapse(self) -> None:
        self.start = None
        self.focus = None
        self.page_index = None
        self._cached_range = None
