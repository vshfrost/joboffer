"""`GET /documents/download/{token}`: одноразове посилання на PDF працює БЕЗ сесії. Ендпоінт — на
справжньому роутері й обробниках помилок, use cases — над in-memory адаптерами й фейковим годинником."""

from datetime import timedelta

import anyio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from domain.documents.document import CoverLetter, Cv
from infrastructure.http.document_downloads import document_downloads_router
from infrastructure.http.errors import install_error_handlers
from tests.support.clock import FakeClock
from tests.support.downloads import CV, LETTER, Library


@pytest.fixture
def library() -> Library:
    return Library(FakeClock())


@pytest.fixture
def client(library: Library) -> TestClient:
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(document_downloads_router(library.downloads))
    return TestClient(app)


def issue(
    library: Library,
    content: Cv | CoverLetter = CV,
    pdf: bytes | None = b"%PDF-1.7 sample",
) -> str:
    """Токен посилання на свіжий документ нового користувача (бази й файлів у цих тестах нема)."""
    owner = library.user("Alex Example")
    number = anyio.run(library.save, owner, content, pdf)
    return anyio.run(library.downloads.create_link, owner, number).token


def test_a_valid_link_gives_the_pdf_once_as_an_attachment_with_its_file_name(
    client: TestClient, library: Library
) -> None:
    token = issue(library)

    response = client.get(f"/documents/download/{token}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        'attachment; filename="Alex_Example_CV.pdf"'
    )
    assert response.headers["cache-control"] == "no-store"
    assert response.content == b"%PDF-1.7 sample"


def test_a_valid_link_answer_may_be_read_cross_origin_by_a_page_in_the_users_browser(
    client: TestClient, library: Library
) -> None:
    token = issue(library)

    response = client.get(f"/documents/download/{token}")

    assert response.headers["access-control-allow-origin"] == "*"


def test_a_cover_letter_link_has_the_cover_letter_file_name(
    client: TestClient, library: Library
) -> None:
    token = issue(library, LETTER)

    response = client.get(f"/documents/download/{token}")

    assert response.headers["content-disposition"] == (
        'attachment; filename="Alex_Example_Cover_Letter.pdf"'
    )


def test_the_same_link_a_second_time_is_not_found(
    client: TestClient, library: Library
) -> None:
    token = issue(library)
    assert client.get(f"/documents/download/{token}").status_code == 200

    again = client.get(f"/documents/download/{token}")

    assert (again.status_code, again.json()["code"]) == (404, "not_found")


def test_the_link_after_ten_minutes_is_not_found(
    client: TestClient, library: Library
) -> None:
    token = issue(library)
    library.clock.advance(timedelta(minutes=10))

    late = client.get(f"/documents/download/{token}")

    assert (late.status_code, late.json()["code"]) == (404, "not_found")


def test_the_link_within_ten_minutes_still_gives_the_pdf(
    client: TestClient, library: Library
) -> None:
    token = issue(library)
    library.clock.advance(timedelta(minutes=9, seconds=59))

    assert client.get(f"/documents/download/{token}").status_code == 200


def test_unknown_used_expired_and_fileless_links_answer_exactly_alike(
    client: TestClient, library: Library
) -> None:
    used = issue(library)
    client.get(f"/documents/download/{used}")
    expired = issue(library)
    library.clock.advance(timedelta(minutes=10))
    fileless = issue(library, CV, None)

    answers = {
        (r.status_code, r.text)
        for r in (
            client.get(f"/documents/download/{token}")
            for token in ("unknown", used, expired, fileless)
        )
    }

    assert len(answers) == 1
    assert next(iter(answers))[0] == 404
