"""Unit tests for search result highlighting filtering logic."""

from src.core.state.app_state import (
    SearchResult,
    ResultCategory,
    HighlightMode,
    HighlightFilter,
)
from src.controllers.redaction.rendering_controller import (
    get_highlight_mode,
    should_highlight_result,
    filter_results_for_page,
)


class TestGetHighlightMode:
    """Tests for get_highlight_mode() pure function."""

    def test_empty_string_returns_all_terms(self) -> None:
        assert get_highlight_mode("") == HighlightMode.ALL_TERMS

    def test_all_string_returns_all_terms(self) -> None:
        assert get_highlight_mode("All") == HighlightMode.ALL_TERMS
        assert get_highlight_mode("all") == HighlightMode.ALL_TERMS
        assert get_highlight_mode("ALL") == HighlightMode.ALL_TERMS

    def test_whitespace_returns_all_terms(self) -> None:
        assert get_highlight_mode("  ") == HighlightMode.ALL_TERMS
        assert get_highlight_mode(" All ") == HighlightMode.ALL_TERMS

    def test_specific_term_returns_single_term(self) -> None:
        assert get_highlight_mode("confidential") == HighlightMode.SINGLE_TERM
        assert get_highlight_mode("SSN") == HighlightMode.SINGLE_TERM


class TestShouldHighlightResult:
    """Tests for should_highlight_result() pure function."""

    def test_different_file_returns_false(self) -> None:
        result = SearchResult(
            id="test-id-1",
            category=ResultCategory.MATCHES,
            file_name="doc1.pdf",
            file_path="/doc1.pdf",
            page=5,
            match="test",
            term="test",
            context="",
            batch_id="",
            redacted=False,
            dismissed=False,
        )
        filter_cfg = HighlightFilter(
            current_file="doc2.pdf", current_page=5, mode=HighlightMode.ALL_TERMS
        )
        assert should_highlight_result(result, filter_cfg) is False

    def test_different_page_returns_false(self) -> None:
        result = SearchResult(
            id="test-id",
            category=ResultCategory.MATCHES,
            file_name="doc.pdf",
            file_path="/doc.pdf",
            page=5,
            match="test",
            term="test",
            context="",
            batch_id="",
            redacted=False,
            dismissed=False,
        )
        filter_cfg = HighlightFilter(
            current_file="doc.pdf", current_page=10, mode=HighlightMode.ALL_TERMS
        )
        assert should_highlight_result(result, filter_cfg) is False

    def test_redacted_result_returns_false(self) -> None:
        result = SearchResult(
            id="test-id",
            category=ResultCategory.MATCHES,
            file_name="doc.pdf",
            file_path="/doc.pdf",
            page=5,
            match="test",
            term="test",
            context="",
            batch_id="",
            redacted=True,
            dismissed=False,
        )
        filter_cfg = HighlightFilter(
            current_file="doc.pdf", current_page=5, mode=HighlightMode.ALL_TERMS
        )
        assert should_highlight_result(result, filter_cfg) is False

    def test_dismissed_result_returns_false(self) -> None:
        result = SearchResult(
            id="test-id",
            category=ResultCategory.MATCHES,
            file_name="doc.pdf",
            file_path="/doc.pdf",
            page=5,
            match="test",
            term="test",
            context="",
            batch_id="",
            redacted=False,
            dismissed=True,
        )
        filter_cfg = HighlightFilter(
            current_file="doc.pdf", current_page=5, mode=HighlightMode.ALL_TERMS
        )
        assert should_highlight_result(result, filter_cfg) is False

    def test_all_terms_mode_returns_true(self) -> None:
        result = SearchResult(
            id="test-id",
            category=ResultCategory.MATCHES,
            file_name="doc.pdf",
            file_path="/doc.pdf",
            page=5,
            match="CONFIDENTIAL",
            term="confidential",
            context="",
            batch_id="",
            redacted=False,
            dismissed=False,
        )
        filter_cfg = HighlightFilter(
            current_file="doc.pdf", current_page=5, mode=HighlightMode.ALL_TERMS
        )
        assert should_highlight_result(result, filter_cfg) is True

    def test_single_term_mode_matches_term(self) -> None:
        result = SearchResult(
            id="test-id",
            category=ResultCategory.MATCHES,
            file_name="doc.pdf",
            file_path="/doc.pdf",
            page=5,
            match="CONFIDENTIAL",
            term="confidential",
            context="",
            batch_id="",
            redacted=False,
            dismissed=False,
        )
        filter_cfg = HighlightFilter(
            current_file="doc.pdf",
            current_page=5,
            mode=HighlightMode.SINGLE_TERM,
            term="confidential",
        )
        assert should_highlight_result(result, filter_cfg) is True

    def test_single_term_mode_matches_matched_text(self) -> None:
        result = SearchResult(
            id="test-id",
            category=ResultCategory.MATCHES,
            file_name="doc.pdf",
            file_path="/doc.pdf",
            page=5,
            match="CONFIDENTIAL",
            term="confidential",
            context="",
            batch_id="",
            redacted=False,
            dismissed=False,
        )
        filter_cfg = HighlightFilter(
            current_file="doc.pdf",
            current_page=5,
            mode=HighlightMode.SINGLE_TERM,
            term="CONFIDENTIAL",  # Match against matched text
        )
        assert should_highlight_result(result, filter_cfg) is True

    def test_single_term_mode_case_insensitive(self) -> None:
        result = SearchResult(
            id="test-id",
            category=ResultCategory.MATCHES,
            file_name="doc.pdf",
            file_path="/doc.pdf",
            page=5,
            match="Confidential",
            term="confidential",
            context="",
            batch_id="",
            redacted=False,
            dismissed=False,
        )
        filter_cfg = HighlightFilter(
            current_file="doc.pdf",
            current_page=5,
            mode=HighlightMode.SINGLE_TERM,
            term="CONFIDENTIAL",
        )
        assert should_highlight_result(result, filter_cfg) is True

    def test_single_term_mode_no_match_returns_false(self) -> None:
        result = SearchResult(
            id="test-id",
            category=ResultCategory.MATCHES,
            file_name="doc.pdf",
            file_path="/doc.pdf",
            page=5,
            match="SSN",
            term="ssn",
            context="",
            batch_id="",
            redacted=False,
            dismissed=False,
        )
        filter_cfg = HighlightFilter(
            current_file="doc.pdf",
            current_page=5,
            mode=HighlightMode.SINGLE_TERM,
            term="confidential",
        )
        assert should_highlight_result(result, filter_cfg) is False


class TestFilterResultsForPage:
    """Tests for filter_results_for_page() pure function."""

    def test_empty_list_returns_empty(self) -> None:
        filter_cfg = HighlightFilter(
            current_file="doc.pdf", current_page=5, mode=HighlightMode.ALL_TERMS
        )
        assert filter_results_for_page([], filter_cfg) == []

    def test_filters_by_page(self) -> None:
        results = [
            SearchResult(
                id="test-id",
                category=ResultCategory.MATCHES,
                file_name="doc.pdf",
                file_path="/doc.pdf",
                page=5,
                match="A",
                term="a",
                context="",
                batch_id="",
                redacted=False,
                dismissed=False,
            ),
            SearchResult(
                id="test-id",
                category=ResultCategory.MATCHES,
                file_name="doc.pdf",
                file_path="/doc.pdf",
                page=10,
                match="B",
                term="b",
                context="",
                batch_id="",
                redacted=False,
                dismissed=False,
            ),
        ]
        filter_cfg = HighlightFilter(
            current_file="doc.pdf", current_page=5, mode=HighlightMode.ALL_TERMS
        )
        filtered = filter_results_for_page(results, filter_cfg)
        assert len(filtered) == 1
        assert filtered[0].match == "A"

    def test_filters_by_redaction_status(self) -> None:
        results = [
            SearchResult(
                id="test-id",
                category=ResultCategory.MATCHES,
                file_name="doc.pdf",
                file_path="/doc.pdf",
                page=5,
                match="A",
                term="a",
                context="",
                batch_id="",
                redacted=False,
                dismissed=False,
            ),
            SearchResult(
                id="test-id",
                category=ResultCategory.MATCHES,
                file_name="doc.pdf",
                file_path="/doc.pdf",
                page=5,
                match="B",
                term="b",
                context="",
                batch_id="",
                redacted=True,
                dismissed=False,
            ),
        ]
        filter_cfg = HighlightFilter(
            current_file="doc.pdf", current_page=5, mode=HighlightMode.ALL_TERMS
        )
        filtered = filter_results_for_page(results, filter_cfg)
        assert len(filtered) == 1
        assert filtered[0].match == "A"
