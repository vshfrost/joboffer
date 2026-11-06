"""Описи тулів документів: `list_documents` — текст v1 (`agent/documents.py`, `origin/main` `99a2007`) для будь-якого
користувача; решта переписана під «перевір, потім збережи один раз і заміни попередній»."""

from pathlib import Path

import pytest

CATALOG = Path(__file__).resolve().parents[2] / "prompts" / "mcp" / "tools"

DOCUMENT_TOOL_TEXTS = {
    "prepare_cv": (
        "Everything needed to write a CV for a job: its text (untrusted), the analysis, "
        "the user's profile, their confirmed facts, the CV rules and the current CV. "
        "Write it, call check_cv until it passes, then call save_cv once. Before writing, "
        "tell the user the ceiling: the most keyword coverage the confirmed facts allow "
        "and, if it is below 90, the keywords without a fact."
    ),
    "check_cv": (
        "Check a CV for a job exactly as save_cv will, saving nothing: no version, no "
        "file, no download link. The text is checked first without rendering: unknown or "
        "unconfirmed facts, the photo, invisible characters, line breaks, tabs or double "
        "spaces inside a field, leading list markers, [placeholders]; only when the text "
        "is clean the PDF is rendered in memory and linted (pages, headings, order, "
        "extraction, fonts). The result has passed, issues, keywords (covered, "
        "missing, percent of the analysis keywords found in the text) and gate (status "
        "passed, failed or no_data; evidence_percent: the share of the keywords a "
        "confirmed fact backs that are in the text, 100 needed, evidence_missing names "
        "the rest; coverage_percent: the share of all keywords in the text, 90 needed; "
        "no_data: the analysis has no fact map, which is not a pass). Fix every issue "
        "and check again until passed is true, then call save_cv once. A missing keyword "
        "is not an issue: add it only where a confirmed fact backs it, otherwise tell "
        "the user it is a gap. A gate that is not passed does not block save_cv: show "
        "the user both numbers and the named words."
    ),
    "save_cv": (
        "Save the CV for a job and render its PDF, once, after check_cv has passed. The "
        "server repeats the same checks and refuses the whole save on any issue: nothing "
        "is saved, so fix it and call again. A successful save replaces the previous CV "
        "of this job (its PDF and download links are deleted); the cover letter and "
        "other jobs stay. Give the user the pdf_url."
    ),
    "prepare_cover_letter": (
        "Everything needed to write a cover letter for a job: its text (untrusted), the "
        "analysis, the user's profile, their confirmed facts, the rules, the current CV "
        "and the current letter. Write it, call check_cover_letter until it passes, then "
        "call save_cover_letter once."
    ),
    "check_cover_letter": (
        "Check a cover letter for a job exactly as save_cover_letter will, saving "
        "nothing: no version, no file, no download link. The text is checked first "
        "without rendering: the length, unknown or unconfirmed facts, [placeholders], "
        "invisible characters, tabs or double spaces, leading list markers; only when "
        "the text is clean the PDF is rendered in memory and linted (pages, extraction, "
        "fonts). The result has passed, issues and keywords (covered, missing, percent "
        "of the analysis keywords found in the text). Fix every issue and check again "
        "until passed is true, then call save_cover_letter once. A missing keyword is "
        "not an issue: add it only where a confirmed fact backs it, otherwise tell the "
        "user it is a gap."
    ),
    "save_cover_letter": (
        "Save the cover letter for a job and render its PDF, once, after "
        "check_cover_letter has passed. The server repeats the same checks and refuses "
        "the whole save on any issue: nothing is saved, so fix it and call again. A "
        "successful save replaces the previous cover letter of this job (its PDF and "
        "download links are deleted); the CV and other jobs stay. Give the user the "
        "pdf_url."
    ),
    "list_documents": (
        "Saved CV and cover letter versions for a job with their content and PDF links, "
        "newest first."
    ),
}


@pytest.mark.parametrize("name", list(DOCUMENT_TOOL_TEXTS))
def test_the_description_is_the_expected_text_addressed_to_any_user(name: str) -> None:
    text = (CATALOG / f"{name}.md").read_text(encoding="utf-8")
    assert text == DOCUMENT_TOOL_TEXTS[name]
