"""HTTP: тексти умов і політики віддаються без сесії, версія одна на документ, текст — звичайний текст."""

import re

import pytest
from fastapi.testclient import TestClient

from bootstrap.api import create_app
from bootstrap.settings import Settings

VERSION = re.compile(r"\d{4}-\d{2}-\d{2}\.\d+")


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(environment="test")))


@pytest.mark.parametrize("doc", ["terms", "privacy"])
def test_document_is_served_without_session(client: TestClient, doc: str) -> None:
    response = client.get(f"/legal/{doc}")
    assert response.status_code == 200
    body = response.json()
    assert (body["doc"], sorted(body)) == (doc, ["doc", "text", "version"])


@pytest.mark.parametrize("doc", ["terms", "privacy"])
def test_document_carries_a_version_number(client: TestClient, doc: str) -> None:
    assert VERSION.fullmatch(client.get(f"/legal/{doc}").json()["version"])


@pytest.mark.parametrize("doc", ["terms", "privacy"])
def test_version_is_stable_between_requests(client: TestClient, doc: str) -> None:
    first = client.get(f"/legal/{doc}").json()["version"]
    assert client.get(f"/legal/{doc}").json()["version"] == first


@pytest.mark.parametrize("doc", ["terms", "privacy"])
def test_text_is_plain_text_without_html_or_front_matter(
    client: TestClient, doc: str
) -> None:
    text = client.get(f"/legal/{doc}").json()["text"]
    assert text.strip() != ""
    assert re.search(r"<[A-Za-z/!]", text) is None
    assert not text.startswith("---")


def test_privacy_says_data_is_deleted_on_request(client: TestClient) -> None:
    text = client.get("/legal/privacy").json()["text"]
    assert "видаляємо на запит" in text


def test_terms_and_privacy_are_different_documents(client: TestClient) -> None:
    terms = client.get("/legal/terms").json()["text"]
    assert terms != client.get("/legal/privacy").json()["text"]


@pytest.mark.parametrize("doc", ["cookies", "TERMS", "terms.md", "..%2Fterms", ""])
def test_unknown_document_is_404(client: TestClient, doc: str) -> None:
    assert client.get(f"/legal/{doc}").status_code == 404


def test_only_get_is_allowed(client: TestClient) -> None:
    assert client.post("/legal/terms").status_code == 405
