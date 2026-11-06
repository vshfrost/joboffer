"""Контакти для шапки CV."""

from dataclasses import dataclass
from typing import Self

from domain.profile.text import one_line
from domain.shared.problems import Problems

MAX_CONTACT_LENGTH = 200
CONTACT_FIELDS = (
    "full_name",
    "email",
    "phone",
    "linkedin_url",
    "city",
    "github_url",
    "work_authorization",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ContactsDraft:
    """Контакти з вводу: ще не перевірені."""

    full_name: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    city: str = ""
    github_url: str = ""
    work_authorization: str = ""


@dataclass(frozen=True, slots=True)
class Contacts:
    full_name: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    city: str = ""
    github_url: str = ""
    work_authorization: str = ""

    @classmethod
    def parse(cls, draft: ContactsDraft) -> Self:
        contacts = cls(
            full_name=one_line(draft.full_name),
            email=draft.email.strip(),
            phone=one_line(draft.phone),
            linkedin_url=draft.linkedin_url.strip(),
            city=one_line(draft.city),
            github_url=draft.github_url.strip(),
            work_authorization=one_line(draft.work_authorization),
        )
        problems = Problems()
        for name in CONTACT_FIELDS:
            if len(getattr(contacts, name)) > MAX_CONTACT_LENGTH:
                problems.add(name, f"{name} — до {MAX_CONTACT_LENGTH} символів.")
        local, _, domain = contacts.email.partition("@")
        if contacts.email and not (
            local and "." in domain and " " not in contacts.email
        ):
            problems.add("email", "Email виглядає некоректно, напр. name@example.com.")
        if contacts.linkedin_url and not contacts.linkedin_url.startswith("https://"):
            problems.add("linkedin_url", "LinkedIn — посилання з https://.")
        if contacts.github_url and not contacts.github_url.startswith("https://"):
            problems.add("github_url", "GitHub — посилання з https://.")
        problems.raise_if_any()
        return contacts
