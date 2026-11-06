"""Значення, якими рубрика аналізу підставляється в шаблон: ім'я кандидата й приклади доменів."""

from dataclasses import dataclass

from domain.profile.profile import Profile

NEUTRAL_CANDIDATE = "the candidate"


@dataclass(frozen=True, slots=True)
class RubricValues:
    candidate: str
    domain_examples: str


def rubric_values(profile: Profile) -> RubricValues:
    """Ім'я кандидата — з контактів профілю, приклади — з цільових доменів; порожній профіль —
    нейтральні формулювання."""
    domains = profile.target.target_domains
    return RubricValues(
        candidate=profile.contacts.full_name or NEUTRAL_CANDIDATE,
        domain_examples=f" (e.g. {', '.join(domains)})" if domains else "",
    )
