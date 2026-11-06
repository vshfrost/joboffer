"""Правила CV і листа в `app/prompts/documents/`: текст v1 (разом з ATS-правилами 3f17f5) для будь-якого
користувача, доповнений процедурою покриття ключових слів, гігієною тексту й перевіркою перед збереженням."""

import re
from pathlib import Path

from application.ports.prompts import PromptKey
from infrastructure.prompts.catalog import FilePrompts
from tests.support.v1_document_rules import V1_COVER_LETTER_RULES, V1_CV_RULES

CATALOG = Path(__file__).resolve().parents[2] / "prompts"
NAMING = re.compile(r"\b(Taras|he|his|him|himself)\b")
# Правило про фото в шапці CV: у v1 звертається до іменованого власника, у v2 — до будь-якого користувача.
V1_PHOTO_RULE = (
    "- Photo: before save_cv show Taras his photos (preview_url) and suggest suggested_photo_id or no photo;\n"
    "  for jobs in the UK, US, Ireland or Canada suggest no photo (photos in CVs are discouraged there).\n"
    "  Pass the photo_id he picks; null means no photo. No photos yet → give him photo_upload_url.\n"
)
NEUTRAL_PHOTO_RULE = (
    "- Photo: before save_cv show the user their photos (preview_url) and suggest suggested_photo_id or no photo;\n"
    "  for jobs in the UK, US, Ireland or Canada suggest no photo (photos in CVs are discouraged there).\n"
    "  Pass the photo_id they pick; null means no photo. No photos yet → give them photo_upload_url.\n"
)


def _rules(key: PromptKey) -> str:
    return FilePrompts.load(CATALOG).get(key)


def _neutral(v1: str) -> str:
    return (
        v1.replace(V1_PHOTO_RULE, NEUTRAL_PHOTO_RULE)
        .replace("Taras's", "the candidate's")
        .replace("about Taras", "about the candidate")
    )


def _flat(text: str) -> str:
    return " ".join(text.split())


def _keeps_every_line_in_order(v1: str, current: str) -> bool:
    remaining = iter(current.splitlines())
    return all(line in remaining for line in v1.splitlines())


def test_cv_rules_keep_the_v1_text_addressed_to_any_user_with_the_photo_rule() -> None:
    v1_without_replaced_line = _neutral(V1_CV_RULES).replace(
        " Skip facts irrelevant to the job.", ""
    )
    assert _keeps_every_line_in_order(
        v1_without_replaced_line, _rules(PromptKey.DOCUMENTS_CV_RULES)
    )
    assert NEUTRAL_PHOTO_RULE in _rules(PromptKey.DOCUMENTS_CV_RULES)


def test_cover_letter_rules_keep_the_v1_text_addressed_to_any_user() -> None:
    assert _keeps_every_line_in_order(
        _neutral(V1_COVER_LETTER_RULES), _rules(PromptKey.DOCUMENTS_COVER_LETTER_RULES)
    )


def test_cv_rules_have_the_keyword_coverage_procedure() -> None:
    text = _flat(_rules(PromptKey.DOCUMENTS_CV_RULES))

    assert (
        "build a map of every analysis keyword and every hard requirement or tool "
        "named in the posting → the confirmed facts that back it" in text
    )
    assert "appears in the CV in the exact form of the posting" in text
    assert "aim at 100 % of the backed keywords" in text
    assert "both in Skills and in the Experience bullets" in text
    assert "and in the headline or summary where it reads naturally" in text
    assert 'write both together, e.g. "Continuous Integration (CI)"' in text
    assert "Never insert a keyword no fact backs" in text
    assert "tell the user about it as a gap" in text


def test_cv_rules_no_longer_tell_to_skip_facts_irrelevant_to_the_job() -> None:
    text = _flat(_rules(PromptKey.DOCUMENTS_CV_RULES))

    assert "Skip facts irrelevant to the job" not in text
    assert "irrelevant" not in text


def test_cv_rules_fill_free_space_with_the_strongest_facts_after_job_keywords() -> None:
    text = _flat(_rules(PromptKey.DOCUMENTS_CV_RULES))
    keywords_first = "first cover every job keyword that has a fact"
    strong_facts = (
        "add the strongest confirmed facts even if the posting does not mention them: "
        "a measurable result, scale, a responsibility, production reliability"
    )

    assert "Lead bullets with impact and numbers." in text
    assert "when all of them are already in the CV and space is left" in text
    assert keywords_first in text
    assert strong_facts in text
    assert text.index(keywords_first) < text.index(strong_facts)
    assert "A strong fact never displaces a job keyword with a fact." in text


def test_cv_rules_keep_the_fact_and_length_rules_with_strong_facts() -> None:
    text = _flat(_rules(PromptKey.DOCUMENTS_CV_RULES))

    assert "ATS-friendly, one to two pages." in text
    assert "Never state what no fact backs: no invented numbers" in text
    assert "keep numbers, names and dates exactly as in the facts" in text
    assert "up to two pages" in text
    assert "every added fact is listed in fact_ids" in text


def test_cv_rules_have_the_text_hygiene_rules_and_the_check_step() -> None:
    text = _flat(_rules(PromptKey.DOCUMENTS_CV_RULES))

    assert "no line breaks, tabs, invisible characters or double spaces" in text
    assert 'no "•" or "-" at the start of a bullet' in text
    assert 'no "[...]" placeholders' in text
    assert "Call check_cv until passed is true" in text
    assert "then save_cv once: a save replaces the previous CV of this job" in text


def test_cover_letter_rules_mirror_the_keyword_and_hygiene_rules() -> None:
    text = _flat(_rules(PromptKey.DOCUMENTS_COVER_LETTER_RULES))

    assert "work each backed keyword into the letter in the exact form" in text
    assert 'write both together, e.g. "Continuous Integration (CI)"' in text
    assert "Never insert a keyword no fact backs" in text
    assert "no tabs, invisible characters or double spaces" in text
    assert 'no "•" or "-" at the start of a line' in text
    assert 'no "[...]" placeholders' in text
    assert "The only line break inside a paragraph is the one in the sign-off" in text
    assert "Call check_cover_letter until passed is true" in text
    assert "save_cover_letter once" in text


def test_rules_do_not_name_the_owner() -> None:
    for key in (PromptKey.DOCUMENTS_CV_RULES, PromptKey.DOCUMENTS_COVER_LETTER_RULES):
        assert not NAMING.search(_rules(key))


def test_cv_rules_keep_the_ats_rules_of_v1() -> None:
    text = _rules(PromptKey.DOCUMENTS_CV_RULES)

    assert "the job title exactly as the posting names it" in text
    assert "written exactly as in the posting: same form" in text
    assert "not only in Skills" in text
    assert "the server rejects unknown or unconfirmed ids" in text


def test_cover_letter_rules_keep_the_ats_rules_of_v1() -> None:
    text = _rules(PromptKey.DOCUMENTS_COVER_LETTER_RULES)

    assert "150–250 words" in text
    assert "written exactly as in the posting: same form" in text
    assert "concrete example from a specific role" in text
    assert "Best regards,\\nName" in text
