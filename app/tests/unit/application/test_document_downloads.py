"""Одноразові посилання на PDF: агент просить посилання на свій документ, за ним без сесії
можна один раз і лише 10 хвилин забрати файл. Посилання, яке не спрацювало, — це `NotFound`
(однаково для невідомого, використаного, простроченого токена й відсутнього файлу).
"""

import hashlib
from datetime import timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.contracts.actor import Actor
from application.contracts.documents import DownloadLinkData, PdfFileData
from domain.shared.errors import NotFound
from tests.support.clock import FakeClock
from tests.support.downloads import CV, LETTER, Library

NOT_VALID = "Посилання недійсне."


@pytest.fixture
def library(clock: FakeClock) -> Library:
    return Library(clock)


def link(
    portal: BlockingPortal, library: Library, actor: Actor, number: int
) -> DownloadLinkData:
    return portal.call(library.downloads.create_link, actor, number)


def redeem(portal: BlockingPortal, library: Library, token: str) -> PdfFileData:
    return portal.call(library.downloads.redeem, token)


def test_a_valid_link_gives_that_documents_pdf_under_its_recruiter_file_name(
    portal: BlockingPortal, library: Library
) -> None:
    alice = library.user("Alice Example")
    cv = portal.call(library.save, alice, CV, b"%PDF the cv")
    letter = portal.call(library.save, alice, LETTER, b"%PDF the letter")

    cv_link = link(portal, library, alice, cv)
    letter_link = link(portal, library, alice, letter)

    assert redeem(portal, library, letter_link.token) == PdfFileData(
        data=b"%PDF the letter", file_name="Alice_Example_Cover_Letter.pdf"
    )
    assert redeem(portal, library, cv_link.token) == PdfFileData(
        data=b"%PDF the cv", file_name="Alice_Example_CV.pdf"
    )


def test_the_link_names_the_file_and_lives_ten_minutes(
    portal: BlockingPortal, library: Library, clock: FakeClock
) -> None:
    alice = library.user("Alice Example")
    number = portal.call(library.save, alice)

    made = link(portal, library, alice, number)

    assert made.file_name == "Alice_Example_CV.pdf"
    assert made.expires_at == clock.now() + timedelta(minutes=10)
    assert made.token != ""


def test_every_link_has_its_own_token(portal: BlockingPortal, library: Library) -> None:
    alice = library.user("Alice Example")
    number = portal.call(library.save, alice)

    first = link(portal, library, alice, number)
    second = link(portal, library, alice, number)

    assert first.token != second.token


def test_a_link_works_only_once(portal: BlockingPortal, library: Library) -> None:
    alice = library.user("Alice Example")
    token = link(portal, library, alice, portal.call(library.save, alice)).token

    assert redeem(portal, library, token).data == b"%PDF"
    with pytest.raises(NotFound) as error:
        redeem(portal, library, token)

    assert error.value.message == NOT_VALID


def test_a_link_still_works_just_before_ten_minutes_pass(
    portal: BlockingPortal, library: Library, clock: FakeClock
) -> None:
    alice = library.user("Alice Example")
    token = link(portal, library, alice, portal.call(library.save, alice)).token

    clock.advance(timedelta(minutes=9, seconds=59))

    assert redeem(portal, library, token).data == b"%PDF"


def test_a_link_stops_working_after_ten_minutes(
    portal: BlockingPortal, library: Library, clock: FakeClock
) -> None:
    alice = library.user("Alice Example")
    token = link(portal, library, alice, portal.call(library.save, alice)).token

    clock.advance(timedelta(minutes=10))

    with pytest.raises(NotFound) as error:
        redeem(portal, library, token)
    assert error.value.message == NOT_VALID


def test_an_unknown_token_is_not_valid(
    portal: BlockingPortal, library: Library
) -> None:
    with pytest.raises(NotFound) as error:
        redeem(portal, library, "no-such-token")

    assert error.value.message == NOT_VALID


def test_a_missing_pdf_file_is_not_valid_like_any_other_failure(
    portal: BlockingPortal, library: Library
) -> None:
    alice = library.user("Alice Example")
    number = portal.call(library.save, alice, CV, None)
    token = link(portal, library, alice, number).token

    with pytest.raises(NotFound) as error:
        redeem(portal, library, token)

    assert error.value.message == NOT_VALID


def test_a_link_for_a_document_of_another_user_is_not_created(
    portal: BlockingPortal, library: Library
) -> None:
    alice = library.user("Alice Example")
    bob = library.user("Bob Example")
    theirs = portal.call(library.save, bob)

    with pytest.raises(NotFound) as error:
        link(portal, library, alice, theirs)

    assert error.value.message == f"Документ {theirs} не знайдено."
    assert library.links.links == {}


def test_a_link_for_a_document_that_does_not_exist_is_not_created(
    portal: BlockingPortal, library: Library
) -> None:
    alice = library.user("Alice Example")

    with pytest.raises(NotFound) as error:
        link(portal, library, alice, 9)

    assert error.value.message == "Документ 9 не знайдено."
    assert library.links.links == {}


def test_only_the_hash_of_the_token_is_kept(
    portal: BlockingPortal, library: Library
) -> None:
    alice = library.user("Alice Example")
    made = link(portal, library, alice, portal.call(library.save, alice))

    kept = [digest.value for digest in library.links.links]

    assert kept == [hashlib.sha256(made.token.encode()).hexdigest()]
