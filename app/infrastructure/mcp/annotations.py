"""Підказки клієнту про побічні ефекти тулів: є на кожному тулі агента."""

from mcp.types import ToolAnnotations

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
# Кожен виклик створює новий запис (версію документа): повтор — не те саме.
CREATE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)
# Видалення назавжди; повторний виклик нічого не змінює.
DELETE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=True,
    open_world_hint=False,
)
