"""Data models for amendment redaction transfer system."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import TYPE_CHECKING

import fitz

try:
    from rapidfuzz import fuzz

    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    fuzz = None  # type: ignore[assignment]

HAS_FITZ = True

if TYPE_CHECKING:
    pass


@dataclass(slots=True, frozen=True)
class DrawingClusterInfo:
    """Vector drawing cluster bounds and metadata."""

    rect: tuple[float, float, float, float]
    drawing_count: int
    page_num: int

    @property
    def aspect_ratio(self) -> float:
        w = self.rect[2] - self.rect[0]
        h = self.rect[3] - self.rect[1]
        return w / h if h > 0 else 0.0

    @property
    def fitz_rect(self) -> fitz.Rect:
        return fitz.Rect(self.rect)


@dataclass(slots=True, frozen=True)
class DrawingClusterRedaction:
    """Redaction with drawing-cluster-relative coordinates for transfer."""

    page_num: int
    cluster_rect: tuple[float, float, float, float]
    redaction_rect: tuple[float, float, float, float]
    drawing_count: int
    relative_x0: float  # Normalized [0.0-1.0] relative to cluster
    relative_y0: float
    relative_x1: float
    relative_y1: float
    overlap_percentage: float

    def to_json(self) -> str:
        return json.dumps(
            {
                "page_num": self.page_num,
                "cluster_rect": self.cluster_rect,
                "redaction_rect": self.redaction_rect,
                "drawing_count": self.drawing_count,
                "relative_x0": self.relative_x0,
                "relative_y0": self.relative_y0,
                "relative_x1": self.relative_x1,
                "relative_y1": self.relative_y1,
                "overlap_percentage": self.overlap_percentage,
            }
        )

    @classmethod
    def from_json(cls, json_str: str) -> DrawingClusterRedaction:
        data = json.loads(json_str)
        return cls(
            page_num=data["page_num"],
            cluster_rect=tuple(data["cluster_rect"]),
            redaction_rect=tuple(data["redaction_rect"]),
            drawing_count=data["drawing_count"],
            relative_x0=data["relative_x0"],
            relative_y0=data["relative_y0"],
            relative_x1=data["relative_x1"],
            relative_y1=data["relative_y1"],
            overlap_percentage=data["overlap_percentage"],
        )


@dataclass(slots=True, frozen=True)
class CellReference:
    """Reference to a cell and redaction's position relative to it."""

    row: int
    col: int
    cell_bbox: tuple[float, float, float, float]
    cell_text: str
    offset_x: float  # Redaction offset from this cell's top-left
    offset_y: float


@dataclass(slots=True)
class CellMatch:
    """A matched cell with its score and neighbors."""

    page_idx: int
    table_idx: int
    row_idx: int
    col_idx: int
    cell_bbox: tuple[float, float, float, float]
    center_score: float
    up_score: float
    down_score: float
    left_score: float
    right_score: float
    total_score: float
    up_bbox: tuple[float, float, float, float] | None
    down_bbox: tuple[float, float, float, float] | None
    left_bbox: tuple[float, float, float, float] | None
    right_bbox: tuple[float, float, float, float] | None


@dataclass(slots=True)
class TableRedaction:
    """Redaction with table-relative coordinates for transfer."""

    page_num: int
    table_bbox: tuple[float, float, float, float]
    redaction_bbox: tuple[float, float, float, float]
    relative_x0: float  # Normalized [0.0-1.0] relative to table
    relative_y0: float
    relative_x1: float
    relative_y1: float
    col_count: int
    row_count: int
    title: str | None
    headers: list[str]
    top_left_cell: tuple[float, float, float, float] | None
    top_right_cell: tuple[float, float, float, float] | None
    overlap_percentage: float
    redacted_cell_text: str = ""
    adjacency_graph: dict[tuple[int, int], dict[str, str | None]] = field(
        default_factory=dict
    )
    center_cell: CellReference | None = None
    up_cell: CellReference | None = None
    down_cell: CellReference | None = None
    left_cell: CellReference | None = None
    right_cell: CellReference | None = None

    def _cell_ref_to_dict(
        self, cell_ref: CellReference | None
    ) -> dict[str, int | tuple[float, float, float, float] | str | float] | None:
        if cell_ref is None:
            return None
        return {
            "row": cell_ref.row,
            "col": cell_ref.col,
            "cell_bbox": cell_ref.cell_bbox,
            "cell_text": cell_ref.cell_text,
            "offset_x": cell_ref.offset_x,
            "offset_y": cell_ref.offset_y,
        }

    def to_json(self) -> str:
        adjacency_graph_serializable = {
            f"{row},{col}": neighbors
            for (row, col), neighbors in self.adjacency_graph.items()
        }

        return json.dumps(
            {
                "page_num": self.page_num,
                "table_bbox": self.table_bbox,
                "redaction_bbox": self.redaction_bbox,
                "relative_x0": self.relative_x0,
                "relative_y0": self.relative_y0,
                "relative_x1": self.relative_x1,
                "relative_y1": self.relative_y1,
                "col_count": self.col_count,
                "row_count": self.row_count,
                "title": self.title,
                "headers": self.headers,
                "top_left_cell": self.top_left_cell,
                "top_right_cell": self.top_right_cell,
                "overlap_percentage": self.overlap_percentage,
                "redacted_cell_text": self.redacted_cell_text,
                "adjacency_graph": adjacency_graph_serializable,
                "center_cell": self._cell_ref_to_dict(self.center_cell),
                "up_cell": self._cell_ref_to_dict(self.up_cell),
                "down_cell": self._cell_ref_to_dict(self.down_cell),
                "left_cell": self._cell_ref_to_dict(self.left_cell),
                "right_cell": self._cell_ref_to_dict(self.right_cell),
            }
        )

    @classmethod
    def _dict_to_cell_ref(
        cls,
        data: dict[str, int | tuple[float, float, float, float] | str | float] | None,
    ) -> CellReference | None:
        if data is None:
            return None

        row = int(data["row"]) if isinstance(data["row"], (int, float)) else 0
        col = int(data["col"]) if isinstance(data["col"], (int, float)) else 0

        bbox_data = data["cell_bbox"]
        if isinstance(bbox_data, (list, tuple)) and len(bbox_data) == 4:
            cell_bbox = (
                float(bbox_data[0]),
                float(bbox_data[1]),
                float(bbox_data[2]),
                float(bbox_data[3]),
            )
        else:
            cell_bbox = (0.0, 0.0, 0.0, 0.0)

        cell_text = str(data["cell_text"]) if isinstance(data["cell_text"], str) else ""
        offset_x = (
            float(data["offset_x"])
            if isinstance(data["offset_x"], (int, float))
            else 0.0
        )
        offset_y = (
            float(data["offset_y"])
            if isinstance(data["offset_y"], (int, float))
            else 0.0
        )

        return CellReference(
            row=row,
            col=col,
            cell_bbox=cell_bbox,
            cell_text=cell_text,
            offset_x=offset_x,
            offset_y=offset_y,
        )

    @classmethod
    def from_json(cls, json_str: str) -> TableRedaction:
        data = json.loads(json_str)

        adjacency_graph_raw = data.get("adjacency_graph", {})
        adjacency_graph: dict[tuple[int, int], dict[str, str | None]] = {}
        for key, neighbors in adjacency_graph_raw.items():
            parts = key.split(",")
            if len(parts) == 2:
                row, col = int(parts[0]), int(parts[1])
                adjacency_graph[(row, col)] = neighbors

        return cls(
            page_num=data["page_num"],
            table_bbox=tuple(data["table_bbox"]),
            redaction_bbox=tuple(data["redaction_bbox"]),
            relative_x0=data["relative_x0"],
            relative_y0=data["relative_y0"],
            relative_x1=data["relative_x1"],
            relative_y1=data["relative_y1"],
            col_count=data["col_count"],
            row_count=data["row_count"],
            title=data["title"],
            headers=data["headers"],
            top_left_cell=(
                tuple(data["top_left_cell"]) if data["top_left_cell"] else None
            ),
            top_right_cell=(
                tuple(data["top_right_cell"]) if data["top_right_cell"] else None
            ),
            overlap_percentage=data["overlap_percentage"],
            redacted_cell_text=data.get("redacted_cell_text", ""),
            adjacency_graph=adjacency_graph,
            center_cell=cls._dict_to_cell_ref(data.get("center_cell")),
            up_cell=cls._dict_to_cell_ref(data.get("up_cell")),
            down_cell=cls._dict_to_cell_ref(data.get("down_cell")),
            left_cell=cls._dict_to_cell_ref(data.get("left_cell")),
            right_cell=cls._dict_to_cell_ref(data.get("right_cell")),
        )


@dataclass(slots=True, frozen=True)
class TableMatchScore:
    """Multi-factor scoring for matching tables between PDFs."""

    table_idx: int
    structure_score: float
    header_score: float
    title_score: float
    position_score: float
    adjacency_score: float
    total_score: float
    table: fitz.table.Table


@dataclass(slots=True, frozen=True)
class DrawingClusterMatchScore:
    """Multi-factor scoring for matching drawing clusters between PDFs."""

    cluster_info: DrawingClusterInfo
    dimension_score: float
    aspect_score: float
    position_score: float
    count_score: float
    total_score: float
