"""
Persistent UI references for Flet components.

ft.Ref objects are framework-specific and cannot be stored in dataclasses,
so they're maintained here as a global registry.
"""

from __future__ import annotations

import flet as ft

refs: dict[str, ft.Ref[ft.Control]] = {
    "folder_text": ft.Ref[ft.Text](),
    "search_progress": ft.Ref[ft.ProgressBar](),
    "search_status": ft.Ref[ft.Text](),
    "matches_progress": ft.Ref[ft.ProgressBar](),
    "results_list": ft.Ref[ft.ListView](),
    "bookmarks_list": ft.Ref[ft.ListView](),
    "tab_content_area": ft.Ref[ft.Container](),
    "tab_dropdown": ft.Ref[ft.Dropdown](),
    "viewer_stack": ft.Ref[ft.Stack](),
    "pdf_image": ft.Ref[ft.Image](),
    "page_num_txt": ft.Ref[ft.TextField](),
    "total_pages_lbl": ft.Ref[ft.Text](),
    "zoom_lbl": ft.Ref[ft.Text](),
    "context_slider": ft.Ref[ft.Slider](),
    "btn_mode_rect_single": ft.Ref[ft.IconButton](),
    "btn_mode_rect_repeat": ft.Ref[ft.IconButton](),
    "btn_mode_highlight_redact": ft.Ref[ft.IconButton](),
    "btn_mode_highlight_only": ft.Ref[ft.IconButton](),
    "btn_undo": ft.Ref[ft.IconButton](),
    "btn_redo": ft.Ref[ft.IconButton](),
    "btn_tab_collapse": ft.Ref[ft.IconButton](),
    "tab_expand_rail": ft.Ref[ft.Container](),
    "middle_resize_handle_container": ft.Ref[ft.GestureDetector](),
    "dd_results_term_filter": ft.Ref[ft.Dropdown](),
    "terms_table": ft.Ref[ft.DataTable](),
    "new_term_input": ft.Ref[ft.TextField](),
    "export_btn": ft.Ref[ft.IconButton](),
    "left_col": ft.Ref[ft.Container](),
    "mid_col": ft.Ref[ft.Container](),
    "undo_redo_label": ft.Ref[ft.Text](),
    "page_strip_row": ft.Ref[ft.Column](),
    "chk_show_dismissed": ft.Ref[ft.Checkbox](),
    "batch_save_progress": ft.Ref[ft.ProgressBar](),
    "btn_consistency_scan": ft.Ref[ft.ElevatedButton](),
    "consistency_list": ft.Ref[ft.ListView](),
    "consistency_status_indicator": ft.Ref[ft.Container](),
    "viewer_scroll_col": ft.Ref[ft.Column](),
    "left_resize_handle": ft.Ref[ft.GestureDetector](),
    "middle_resize_handle": ft.Ref[ft.GestureDetector](),
    "viewer_list": ft.Ref[ft.ListView](),
    "bookmarks_overlay": ft.Ref[ft.Container](),
    "viewer_loading_overlay": ft.Ref[ft.Container](),
    "dose_results_list": ft.Ref[ft.ListView](),
    "btn_dose_scan": ft.Ref[ft.ElevatedButton](),
    "dose_progress": ft.Ref[ft.ProgressBar](),
    "chk_consistency_show_dismissed": ft.Ref[ft.Checkbox](),
    "ai_detections_list": ft.Ref[ft.ListView](),
    "chk_ai_show_dismissed": ft.Ref[ft.Checkbox](),
    "auth_test_overlay": ft.Ref[ft.Container](),
}
