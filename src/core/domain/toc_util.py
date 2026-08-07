"""Utility functions for working with PDF Table of Contents (TOC/bookmarks)."""

import fitz


def get_section_title_for_page(file_path: str, page_number: int) -> str:
    """Get the section/bookmark title for a given page.

    Args:
        file_path: Path to PDF file
        page_number: Page number (1-based)

    Returns:
        Section title string, or empty string if no bookmark found
    """
    with fitz.open(file_path) as doc:
        toc = doc.get_toc(simple=True)
        if not toc:
            return ""

        # Find the last level-1 bookmark that starts before or at this page
        current_section = ""
        for entry in toc:
            level = int(entry[0])
            title = str(entry[1])
            bookmark_page = int(entry[2])

            if level == 1:
                if bookmark_page <= page_number:
                    current_section = title
                else:
                    break

        return current_section


def get_section_page_range(
    file_path: str, page_number: int
) -> tuple[int, int, str] | None:
    """Get the page range and title for the bookmark section containing the given page.

    Args:
        file_path: Path to PDF file
        page_number: Page number (1-based)

    Returns:
        Tuple of (start_page, end_page, section_title) if found, None otherwise.
        Both page numbers are 1-based and inclusive.
    """
    import logging

    logger = logging.getLogger(__name__)

    logger.info(
        f"get_section_page_range called: file={file_path}, page_number={page_number}"
    )
    with fitz.open(file_path) as doc:
        total_pages = len(doc)
        toc = doc.get_toc(simple=True)
        if not toc:
            return (1, total_pages, "")

        level1_bookmarks = [
            (int(entry[2]), str(entry[1])) for entry in toc if int(entry[0]) == 1
        ]
        level1_bookmarks.sort(key=lambda x: x[0])

        if not level1_bookmarks:
            return (1, total_pages, "")

        section_start = 1
        section_title = ""

        logger.info(f"Level-1 bookmarks (sorted): {level1_bookmarks}")

        for i, (bookmark_page, title) in enumerate(level1_bookmarks):
            if bookmark_page <= page_number:
                section_start = bookmark_page
                section_title = title
                logger.info(
                    f"  Checking bookmark at page {bookmark_page}: '{title}' - matches (page_number={page_number})"
                )
            else:
                logger.info(
                    f"  Checking bookmark at page {bookmark_page}: '{title}' - PAST target page, stopping"
                )
                break

        section_end = total_pages
        for bookmark_page, _ in level1_bookmarks:
            if bookmark_page > section_start:
                section_end = bookmark_page - 1
                break

        logger.info(
            f"Final section: start={section_start}, end={section_end}, title='{section_title}'"
        )
        return (section_start, section_end, section_title)
