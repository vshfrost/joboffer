"""Core (domain, application) повністю імпортується.

Цей тест входить у core-only набір (`scripts/test-core.sh`), де не встановлено жодного
інфраструктурного пакета. Тож імпорт фреймворку в core зламає його реальним ModuleNotFoundError.
"""

import importlib
import pkgutil

import pytest

CORE = ("domain", "application")


def _walk(package_name: str) -> list[str]:
    package = importlib.import_module(package_name)
    return [package_name] + [
        m.name
        for m in pkgutil.walk_packages(package.__path__, prefix=f"{package_name}.")
    ]


@pytest.mark.parametrize("core", CORE)
def test_core_modules_import(core: str) -> None:
    for name in _walk(core):
        importlib.import_module(name)
