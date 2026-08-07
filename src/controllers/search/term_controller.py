from __future__ import annotations

import os
from typing import Protocol

import flet as ft

from src.core.domain.excel_export import export_terms_to_excel, import_terms_from_excel
from src.core.state.app_state import TermItem
from src.core.state.ui_state import refs
from src.ui.views import files_view


class MainControllerProtocol(Protocol):
    terms_list: list[TermItem]
    page: object


class TermController:
    def __init__(self, main_controller: MainControllerProtocol, page: ft.Page) -> None:
        self.main_controller: MainControllerProtocol = main_controller
        self.page: ft.Page = page

    def _save_terms_to_storage(self) -> None:
        # TermItem has slots=True, so convert to dicts for client storage
        terms_dicts = [
            {"term": t.term, "active": t.active}
            for t in self.main_controller.terms_list
        ]
        self.page.client_storage.set("terms_list", terms_dicts)

    @property
    def terms_list(self) -> list[TermItem]:
        return self.main_controller.terms_list

    @terms_list.setter
    def terms_list(self, value: list[TermItem]) -> None:
        self.main_controller.terms_list = value

    def refresh_term_table(self) -> None:
        terms_table_ref = refs.get("terms_table")
        if not terms_table_ref:
            return
        table = terms_table_ref.current
        if not table:
            return
        table.rows.clear()

        def on_toggle(idx: int, val: bool) -> None:
            from dataclasses import replace

            self.terms_list[idx] = replace(self.terms_list[idx], active=val)
            self._save_terms_to_storage()

        def on_delete(idx: int) -> None:
            del self.terms_list[idx]
            self._save_terms_to_storage()
            self.refresh_term_table()

        for i, item in enumerate(self.terms_list):
            table.rows.append(
                files_view.build_term_table_row(
                    index=i,
                    term=item.term,
                    active=item.active,
                    on_toggle=on_toggle,
                    on_delete=on_delete,
                )
            )
        self.page.update()

    def add_term(self, e: ft.ControlEvent) -> None:
        new_term_input_ref = refs.get("new_term_input")
        if not new_term_input_ref:
            return
        input_ctl = new_term_input_ref.current
        if not input_ctl:
            return
        val = (input_ctl.value or "").strip()
        if not val:
            return

        for t in self.terms_list:
            if t.term.lower() == val.lower():
                input_ctl.value = ""
                self.page.update()
                return

        self.terms_list.append(TermItem(term=val, active=True))
        input_ctl.value = ""
        self._save_terms_to_storage()
        self.refresh_term_table()

    def export_terms_to_excel(self, _: ft.ControlEvent) -> None:
        if not self.terms_list:
            self.page.open(ft.SnackBar(ft.Text("No terms to export."), bgcolor="grey"))
            return

        def on_save_result(e: ft.FilePickerResultEvent) -> None:
            if not e.path:
                return
            path = e.path
            if not path.lower().endswith(".xlsx"):
                path += ".xlsx"

            terms_dicts: list[dict[str, str | bool]] = [
                {"term": t.term, "active": t.active} for t in self.terms_list
            ]
            success = export_terms_to_excel(terms_dicts, path)
            if success:
                self.page.open(
                    ft.SnackBar(
                        ft.Text(
                            f"Exported {len(self.terms_list)} terms to {os.path.basename(path)}"
                        ),
                        bgcolor="green",
                    )
                )
            else:
                self.page.open(
                    ft.SnackBar(ft.Text("Failed to export terms."), bgcolor="red")
                )

        picker = ft.FilePicker(on_result=on_save_result)
        self.page.overlay.append(picker)
        self.page.update()
        picker.save_file(
            dialog_title="Export Terms to Excel",
            file_name="search_terms.xlsx",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx"],
        )

    def import_terms_from_excel(self, _: ft.ControlEvent) -> None:
        def on_file_result(e: ft.FilePickerResultEvent) -> None:
            if not e.files or not e.files[0].path:
                return
            file_path = e.files[0].path
            imported_terms = import_terms_from_excel(file_path)
            if not imported_terms:
                self.page.open(
                    ft.SnackBar(
                        ft.Text("No terms found in file or error reading file."),
                        bgcolor="orange",
                    )
                )
                return

            def do_merge(_: ft.ControlEvent) -> None:
                existing_terms_lower: set[str] = {
                    t.term.lower() for t in self.terms_list
                }

                added = 0
                for term in imported_terms:
                    if term.lower() not in existing_terms_lower:
                        self.terms_list.append(TermItem(term=term, active=True))
                        existing_terms_lower.add(term.lower())
                        added += 1
                self._save_terms_to_storage()
                self.refresh_term_table()
                dlg.open = False
                self.page.update()
                self.page.open(
                    ft.SnackBar(
                        ft.Text(f"Added {added} new terms (merged with existing)."),
                        bgcolor="green",
                    )
                )

            def do_replace(_: ft.ControlEvent) -> None:
                self.terms_list.clear()
                for term in imported_terms:
                    self.terms_list.append(TermItem(term=term, active=True))
                self._save_terms_to_storage()
                self.refresh_term_table()
                dlg.open = False
                self.page.update()
                self.page.open(
                    ft.SnackBar(
                        ft.Text(f"Replaced with {len(imported_terms)} terms."),
                        bgcolor="green",
                    )
                )

            def do_cancel(_: ft.ControlEvent) -> None:
                dlg.open = False
                self.page.update()

            dlg = files_view.build_import_dialog(
                imported_count=len(imported_terms),
                on_merge=do_merge,
                on_replace=do_replace,
                on_cancel=do_cancel,
            )
            self.page.overlay.append(dlg)
            dlg.open = True
            self.page.update()

        picker = ft.FilePicker(on_result=on_file_result)
        self.page.overlay.append(picker)
        self.page.update()
        picker.pick_files(
            dialog_title="Import Terms from Excel",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx", "xls"],
            allow_multiple=False,
        )
