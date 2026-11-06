"""Application contracts: DTO, Actor, integration envelopes (plain dataclasses).

Конвенція команд (REST і MCP користуються одними use cases):
- кожен dataclass тут — `frozen=True` (це перевіряє тест);
- поля команд — примітиви: `str`, `int`, `date`, `None` та `UNSET` з `domain.shared.patch`
  («не передано» ≠ `None` «очистити» ≠ значення);
- value objects і typed ID будує use case, а не транспорт: валідація в одному місці;
- `Actor` збирають лише вхідні адаптери з перевіреної identity, ніколи з тіла запиту.
"""
