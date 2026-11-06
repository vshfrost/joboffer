"""Хешування паролів: Argon2id (argon2-cffi з типовими параметрами RFC 9106, low-memory).

Параметри записані в самому хеші, тож їх можна змінити, не ламаючи старі хеші.
Обчислення синхронне й важке — виконується в потоці, щоб не блокувати event loop.
"""

import asyncio

from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerificationError

from domain.identity.password import PasswordHash

# Пароль, якого ніхто не вводить: проти його хеша перевіряється ввід, коли користувача нема.
_TIMING_PLACEHOLDER = "placeholder-never-used-as-a-real-password"


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._argon2 = _Argon2()
        self._placeholder: str | None = None

    async def hash(self, raw: str) -> PasswordHash:
        return PasswordHash(await asyncio.to_thread(self._argon2.hash, raw))

    async def verify(self, raw: str, stored: PasswordHash | None) -> bool:
        return await asyncio.to_thread(self._verify, raw, stored)

    def _verify(self, raw: str, stored: PasswordHash | None) -> bool:
        if stored is None:
            self._check(self._placeholder_hash(), raw)
            return False
        return self._check(stored.value, raw)

    def _check(self, encoded: str, raw: str) -> bool:
        try:
            return self._argon2.verify(encoded, raw)
        except VerificationError, InvalidHashError:
            return False

    def _placeholder_hash(self) -> str:
        if self._placeholder is None:
            self._placeholder = self._argon2.hash(_TIMING_PLACEHOLDER)
        return self._placeholder
