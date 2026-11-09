"""Перший екран CV — те, що рекрутер бачить першим: посада, summary, перша група скілів і перший
пункт кожної ролі. Звідси видно розміщення слів, а не лише їхню наявність у CV."""

from dataclasses import dataclass

from domain.documents.document import Cv, CvSectionName


@dataclass(frozen=True, slots=True)
class FirstBullet:
    role: str
    text: str


@dataclass(frozen=True, slots=True)
class FirstScreen:
    headline: str
    summary: str
    # Порожні, коли групи скілів нема.
    skills_label: str
    skills_items: tuple[str, ...]
    first_bullets: tuple[FirstBullet, ...]

    @property
    def lines(self) -> tuple[str, ...]:
        """Текст екрана в порядку читання — для пошуку слів."""
        label = (self.skills_label,) if self.skills_label else ()
        return (
            self.headline,
            self.summary,
            *label,
            *self.skills_items,
            *(bullet.text for bullet in self.first_bullets),
        )


def first_screen(cv: Cv) -> FirstScreen:
    """Перша група Skills — перший пункт секції з пунктами; перший пункт ролі — у секції
    Experience, ролі без пунктів пропускаються."""
    label = ""
    items: tuple[str, ...] = ()
    bullets: list[FirstBullet] = []
    for section in cv.sections:
        if section.name is CvSectionName.SKILLS:
            group = next((entry for entry in section.entries if entry.bullets), None)
            if group is not None:
                label = group.heading.text
                items = tuple(bullet.text for bullet in group.bullets)
        elif section.name is CvSectionName.EXPERIENCE:
            bullets += (
                FirstBullet(entry.heading.text, entry.bullets[0].text)
                for entry in section.entries
                if entry.bullets
            )
    return FirstScreen(cv.headline.text, cv.summary.text, label, items, tuple(bullets))
