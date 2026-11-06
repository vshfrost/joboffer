"""Шари-пакети в корені репо, граф імпортів без циклів."""

import importlib.util

import grimp
import pytest

LAYERS = ("domain", "application", "infrastructure", "bootstrap")


@pytest.mark.parametrize("layer", LAYERS)
def test_layer_is_regular_package(layer: str) -> None:
    spec = importlib.util.find_spec(layer)
    assert spec is not None, f"{layer} не знайдено"
    assert spec.origin is not None, f"{layer} — namespace, а не звичайний пакет"
    assert spec.origin.endswith(f"{layer}/__init__.py")


def test_import_graph_has_no_cycles() -> None:
    graph = grimp.build_graph(*LAYERS)
    cycles = [
        (importer, imported)
        for importer in graph.modules
        for imported in graph.find_modules_directly_imported_by(importer)
        if graph.chain_exists(importer=imported, imported=importer)
    ]
    assert cycles == []
