"""PDF coordinate transformation utilities."""

from dataclasses import dataclass

from src.core.state.app_state import PdfBox


@dataclass(slots=True, frozen=True)
class ScreenBox:
    x: float
    y: float
    w: float
    h: float


def to_pdf_rect(screen_box: ScreenBox, scale_factor: float) -> PdfBox:
    # Division by zero guard: preserve pixel coordinates if scale is zero
    if scale_factor == 0:
        return PdfBox(x=screen_box.x, y=screen_box.y, w=screen_box.w, h=screen_box.h)
    return PdfBox(
        x=screen_box.x / scale_factor,
        y=screen_box.y / scale_factor,
        w=screen_box.w / scale_factor,
        h=screen_box.h / scale_factor,
    )


def to_screen_rect(pdf_box: PdfBox, scale_factor: float) -> ScreenBox:
    return ScreenBox(
        x=pdf_box.x * scale_factor,
        y=pdf_box.y * scale_factor,
        w=pdf_box.w * scale_factor,
        h=pdf_box.h * scale_factor,
    )
