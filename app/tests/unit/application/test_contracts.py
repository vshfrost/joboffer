"""Конвенція application/contracts: усі dataclass незмінні."""

import dataclasses
import importlib
import inspect
import pkgutil

from application import contracts


def _contract_dataclasses() -> list[type]:
    found: list[type] = []
    for module_info in pkgutil.iter_modules(
        contracts.__path__, prefix="application.contracts."
    ):
        module = importlib.import_module(module_info.name)
        found += [
            cls
            for _, cls in inspect.getmembers(module, inspect.isclass)
            if dataclasses.is_dataclass(cls) and cls.__module__ == module.__name__
        ]
    return found


def test_contracts_contain_dataclasses() -> None:
    assert {cls.__name__ for cls in _contract_dataclasses()} >= {"Actor"}


def test_every_contract_dataclass_is_frozen() -> None:
    # frozen=True кладе у клас власний __setattr__, що кидає FrozenInstanceError.
    mutable = [
        cls.__name__
        for cls in _contract_dataclasses()
        if "__setattr__" not in vars(cls)
    ]
    assert mutable == []
