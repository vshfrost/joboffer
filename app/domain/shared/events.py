"""База domain-подій: незмінні факти про зміну агрегата.

Подія не несе часу й автора: їх додає application, коли загортає подію в envelope (event_id,
occurred_at, actor, correlation_id, type, schema_version). У payload лише ідентифікатори й версія,
жодних значень полів, тексту чи токена. Серіалізація й доставка — справа інфраструктури.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    """Спільний предок усіх подій домену; нічого не додає, лише дає тип для `events` агрегатів."""
