"""Ключі лімітів входу: пара «клієнт + email» і окремо email, а не глобальний лічильник.

Пара: зловмисник не заблокує вхід усім, а чужий IP не заблокує власника. Email: верхня межа для
розподіленого підбору з багатьох IP; блок тимчасовий (див. `SessionUseCases`). У ключі лише дайджест:
IP та email не лежать у базі відкритим текстом.
"""

import hashlib
import json


def attempt_key(client: str, email: str) -> str:
    # JSON-список однозначно відокремлює поля: ("a|b", "c") ≠ ("a", "b|c").
    payload = json.dumps([client, email.strip().lower()], ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def login_email_key(email: str) -> str:
    # Невдалі входи на цей email з УСІХ клієнтів: ліміт проти розподіленого підбору пароля. Окремий
    # простір ключів від пари «клієнт + email»; у ключі лише дайджест.
    payload = json.dumps(["login-email", email.strip().lower()], ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def invite_check_key(client: str) -> str:
    # Окремий простір ключів від входу: ті самі `login_failures`, але ключі не перетинаються.
    payload = json.dumps(["signup-invite-check", client], ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def signup_client_key(client: str) -> str:
    # Реєстрації з клієнта. Вікно — година, тож живе в окремому сховищі лімітів реєстрації:
    # `login_failures` чистять вхід і перевірка запрошення кожні 15 хвилин.
    payload = json.dumps(["signup-client", client], ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def signup_mail_key(email: str) -> str:
    # Листи з кодом на адресу (перший і повторні): у ключі лише дайджест, адреси в базі нема.
    payload = json.dumps(["signup-mail", email.strip().lower()], ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()
