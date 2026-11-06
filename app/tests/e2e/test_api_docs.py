"""Інтерактивна документація та схема OpenAPI: у dev є, у prod їх нема."""

import pytest
from fastapi.testclient import TestClient

from bootstrap.api import create_app
from bootstrap.settings import Settings

DOC_PATHS = ["/docs", "/redoc", "/openapi.json"]


@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_and_schema_are_not_served_in_prod(path: str) -> None:
    client = TestClient(create_app(Settings(environment="prod")))

    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_and_schema_stay_available_in_dev(path: str) -> None:
    client = TestClient(create_app(Settings(environment="dev")))

    assert client.get(path).status_code == 200
