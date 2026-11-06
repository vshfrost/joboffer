"""Стеля CV: найбільше покриття слів вакансії, яке можливе лише з підтверджених фактів (треба 90).
Слова без факту під ними — у `unbacked`. Старий аналіз без карти: стелі нема."""

from domain.analysis.keywords import KeywordFacts
from domain.documents.gate import CvCeiling, cv_ceiling


def numbered(count: int) -> tuple[str, ...]:
    return tuple(f"w{number:02d}" for number in range(count))


def map_of(words: tuple[str, ...], fact: int = 1) -> tuple[KeywordFacts, ...]:
    return tuple(KeywordFacts(word, (fact,)) for word in words)


def test_18_of_20_words_backed_give_ceiling_90_and_name_the_other_two() -> None:
    words = numbered(20)

    result = cv_ceiling(words, map_of(words[:18]), (1,))

    assert result == CvCeiling(90, ("w18", "w19"), True)


def test_ceiling_below_90_does_not_reach_the_target_and_names_the_unbacked() -> None:
    words = numbered(10)

    result = cv_ceiling(words, map_of(words[:8]), (1,))

    assert result == CvCeiling(80, ("w08", "w09"), False)


def test_43_of_48_backed_is_89_not_90() -> None:
    words = numbered(48)

    result = cv_ceiling(words, map_of(words[:43]), (1,))

    assert result is not None
    assert (result.percent, result.reaches_target) == (89, False)


def test_a_word_whose_fact_is_not_live_is_unbacked() -> None:
    facts = map_of(("Python",), 1) + map_of(("Kafka",), 2)

    result = cv_ceiling(("Python", "Kafka"), facts, (1,))

    assert result == CvCeiling(50, ("Kafka",), False)


def test_a_new_confirmed_fact_raises_the_ceiling() -> None:
    keywords = ("Python", "Kafka")
    facts = map_of(("Python",), 1) + map_of(("Kafka",), 2)

    before = cv_ceiling(keywords, facts, (1,))
    after = cv_ceiling(keywords, facts, (1, 2))

    assert (before and before.percent, after and after.percent) == (50, 100)


def test_a_group_counts_once_and_is_matched_by_requirement() -> None:
    result = cv_ceiling(
        ("Java | Python", "Kafka"), (KeywordFacts("python|JAVA", (1,)),), (1,)
    )

    assert result == CvCeiling(50, ("Kafka",), False)


def test_no_map_gives_no_ceiling() -> None:
    assert cv_ceiling(("Python",), None, (1,)) is None


def test_no_keywords_gives_no_ceiling() -> None:
    assert cv_ceiling((), (), (1,)) is None
