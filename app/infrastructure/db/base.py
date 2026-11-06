"""ORM-база: усі таблиці адаптера успадковують її, тож Alembic бачить одну metadata.

ORM-класи живуть у `tables.py` свого контексту й виходять назовні лише через mappers.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Передбачувані імена constraint-ів: міграції не залежать від автогенерованих назв.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
