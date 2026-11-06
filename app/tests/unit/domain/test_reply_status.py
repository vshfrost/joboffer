"""Автостатус за листом компанії: лише applied → replied, лише за впевненого збігу від
підтвердженого відправника (verified) і не для автопідтвердження."""

import pytest

from domain.applications.application import ApplicationStatus
from domain.mail.replies import (
    Confidence,
    MatchedBy,
    ReplyMatch,
    ReplyType,
    auto_status,
)
from domain.mail.sender_auth import SenderAuth

HIGH = ReplyMatch(1, Confidence.HIGH, MatchedBy.DOMAIN)
MEDIUM = ReplyMatch(1, Confidence.MEDIUM, MatchedBy.DOMAIN)
LOW = ReplyMatch(1, Confidence.LOW, MatchedBy.NAME)


def test_a_high_confidence_match_from_a_verified_sender_moves_to_replied() -> None:
    assert auto_status(HIGH, ReplyType.REJECTION, SenderAuth.VERIFIED) is (
        ApplicationStatus.REPLIED
    )


def test_a_medium_confidence_match_from_a_verified_sender_moves_to_replied() -> None:
    assert auto_status(MEDIUM, ReplyType.OTHER, SenderAuth.VERIFIED) is (
        ApplicationStatus.REPLIED
    )


def test_an_automatic_confirmation_never_moves_the_status() -> None:
    assert auto_status(HIGH, ReplyType.AUTO_CONFIRMATION, SenderAuth.VERIFIED) is None


def test_a_low_confidence_match_never_moves_the_status() -> None:
    assert auto_status(LOW, ReplyType.INVITATION, SenderAuth.VERIFIED) is None


def test_a_mail_without_a_match_never_moves_the_status() -> None:
    assert auto_status(ReplyMatch(), ReplyType.OTHER, SenderAuth.VERIFIED) is None


@pytest.mark.parametrize("auth", [SenderAuth.UNKNOWN, SenderAuth.FAILED])
def test_an_unverified_sender_never_moves_the_status(auth: SenderAuth) -> None:
    assert auto_status(HIGH, ReplyType.REJECTION, auth) is None
