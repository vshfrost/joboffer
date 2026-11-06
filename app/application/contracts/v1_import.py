"""Команда й звіт імпорту v1 → v2: примітиви."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class ImportV1:
    # False — пробний прогін: усе рахується, нічого не записується.
    apply: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ImportReport:
    applied: bool
    # (таблиця v2, скільки рядків v1 перенесено) у порядку перенесення.
    counts: tuple[tuple[str, int], ...]
    # Номери документів (= id у v1), чиїх PDF у теці нема або тека не задана.
    missing_pdfs: tuple[int, ...]
    # Скільки PDF скопійовано в теку документів v2 (у пробному прогоні — 0).
    pdfs_copied: int
