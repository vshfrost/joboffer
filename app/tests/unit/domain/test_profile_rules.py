"""Правила відбору: три списки без обмежень за довжиною (як у v1)."""

from domain.profile.rules import Rules


def test_empty_rules_mean_no_restriction() -> None:
    parsed = Rules.parse(title_keywords=[], title_exclude=[], stop_words=[])
    assert parsed == Rules()
    assert parsed.title_keywords == ()


def test_each_list_is_trimmed_without_blanks_and_repeats() -> None:
    parsed = Rules.parse(
        title_keywords=[" Backend ", "backend", "", "Python"],
        title_exclude=["Junior", " junior ", "Intern"],
        stop_words=["  relocation ", "RELOCATION"],
    )
    assert parsed.title_keywords == ("Backend", "Python")
    assert parsed.title_exclude == ("Junior", "Intern")
    assert parsed.stop_words == ("relocation",)


def test_the_same_word_may_stay_in_different_lists() -> None:
    parsed = Rules.parse(
        title_keywords=["engineer"], title_exclude=["engineer"], stop_words=[]
    )
    assert parsed.title_keywords == parsed.title_exclude == ("engineer",)
