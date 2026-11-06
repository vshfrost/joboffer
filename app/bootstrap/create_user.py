"""CLI створення користувача: `python -m bootstrap.create_user --email … --name …`.

Пароль питається інтерактивно (getpass) і ніколи не береться з аргументів чи оточення:
він не потрапляє в історію shell, `ps` і логи. Вихідний код 0 — створено, 1 — відмова.
"""

import argparse
import asyncio
import getpass
import sys
from collections.abc import Sequence

from application.contracts.identity import CreateUser
from bootstrap.container import build_container
from bootstrap.settings import Settings
from domain.shared.errors import DomainError


async def _create(settings: Settings, command: CreateUser) -> int:
    container = build_container(settings)
    try:
        view = await container.identity.create_user(command)
    except DomainError as error:
        sys.stderr.write(f"{error.message}\n")
        return 1
    finally:
        await container.engine.dispose()
    sys.stdout.write(f"Користувача створено: {view.email} ({view.id})\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m bootstrap.create_user",
        description="Створити користувача. Пароль буде запитано інтерактивно.",
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True, help="імʼя для відображення")
    args = parser.parse_args(argv)

    password = getpass.getpass("Пароль: ")
    if getpass.getpass("Повтори пароль: ") != password:
        sys.stderr.write("Паролі не збігаються\n")
        return 1
    command = CreateUser(email=args.email, display_name=args.name, password=password)
    return asyncio.run(_create(Settings(), command))


if __name__ == "__main__":
    raise SystemExit(main())
