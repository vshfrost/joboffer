"""Час за місцем користувача: день у Мадриді (Europe/Madrid) для відповідей MCP."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")


def local_day(moment: datetime) -> str:
    """«YYYY-MM-DD» за часом Мадрида: о 00:30 за Мадридом — уже наступний день."""
    return f"{moment.astimezone(MADRID):%Y-%m-%d}"


def local_today(moment: datetime) -> date:
    """Календарний день за часом Мадрида."""
    return moment.astimezone(MADRID).date()


def local_time(moment: datetime) -> datetime:
    """Момент за часом Мадрида (зі зсувом на літній / зимовий час)."""
    return moment.astimezone(MADRID)


def local_minute(moment: datetime) -> str:
    """«YYYY-MM-DD HH:MM» за часом Мадрида."""
    return f"{local_time(moment):%Y-%m-%d %H:%M}"
