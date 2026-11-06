"""Патч поля: відрізняє «не передано» від `None` («очистити») і від значення.

Спільний для domain (edit-методи агрегатів) і application (команди), окремого `Missing` нема.
"""

from enum import Enum, auto


class Unset(Enum):
    """«Поле не передано»: не чіпати."""

    UNSET = auto()


UNSET = Unset.UNSET

type Patch[T] = T | Unset
