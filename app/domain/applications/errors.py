"""Помилки подач."""

from domain.shared.errors import Conflict


class JobHasApplication(Conflict):
    """На вакансію вже є подача: поданих вакансій не ховають."""

    code = "job_has_application"
