"""Use cases altcha: видача задачі, одноразова перевірка розв'язку, закрита реєстрація."""

import base64
import hashlib
import json
from datetime import datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.identity.altcha import AltchaUseCases
from domain.identity.altcha import AltchaPolicy
from domain.identity.errors import AltchaFailed, RegistrationClosed
from tests.support.altcha import (
    TEST_KEY,
    FakeAltchaRandom,
    InMemoryAltchaUnitOfWork,
)
from tests.support.clock import FakeClock

POLICY = AltchaPolicy(key=TEST_KEY, max_number=50_000)


class Setup:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, policy: AltchaPolicy | None
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.random = FakeAltchaRandom()
        self.used: dict[str, datetime] = {}
        self.altcha = AltchaUseCases(
            lambda: InMemoryAltchaUnitOfWork(self.used), clock, self.random, policy
        )

    def solve(self) -> str:
        """Розв'язує видану задачу так, як це робить віджет: перебір 0..maxnumber."""
        challenge = self.portal.call(self.altcha.issue)
        number = next(
            n
            for n in range(challenge.maxnumber + 1)
            if hashlib.sha256(f"{challenge.salt}{n}".encode()).hexdigest()
            == challenge.challenge
        )
        fields = {
            "algorithm": challenge.algorithm,
            "challenge": challenge.challenge,
            "number": number,
            "salt": challenge.salt,
            "signature": challenge.signature,
        }
        return base64.b64encode(json.dumps(fields).encode()).decode()


@pytest.fixture
def setup(portal: BlockingPortal, clock: FakeClock) -> Setup:
    return Setup(portal, clock, POLICY)


def test_issued_challenge_expires_in_five_minutes(setup: Setup) -> None:
    challenge = setup.portal.call(setup.altcha.issue)
    expires = int((setup.clock.now() + timedelta(minutes=5)).timestamp())
    assert challenge.salt == f"00112233445566778899aabb?expires={expires}"


def test_issued_challenge_carries_configured_maxnumber(setup: Setup) -> None:
    challenge = setup.portal.call(setup.altcha.issue)
    assert (challenge.maxnumber, setup.random.asked_max) == (50_000, [50_000])


def test_solved_challenge_is_accepted(setup: Setup) -> None:
    setup.portal.call(setup.altcha.verify, setup.solve())


def test_same_solution_second_time_is_rejected(setup: Setup) -> None:
    payload = setup.solve()
    setup.portal.call(setup.altcha.verify, payload)
    with pytest.raises(AltchaFailed):
        setup.portal.call(setup.altcha.verify, payload)


def test_rejected_solution_is_not_marked_used(setup: Setup) -> None:
    payload = setup.solve()
    with pytest.raises(AltchaFailed):
        setup.portal.call(setup.altcha.verify, payload[:-8] + "AAAAAAAA")
    setup.portal.call(setup.altcha.verify, payload)


def test_solution_after_five_minutes_is_rejected(setup: Setup) -> None:
    payload = setup.solve()
    setup.clock.advance(timedelta(minutes=5, seconds=1))
    with pytest.raises(AltchaFailed):
        setup.portal.call(setup.altcha.verify, payload)


def test_expired_used_solutions_are_forgotten(setup: Setup) -> None:
    setup.portal.call(setup.altcha.verify, setup.solve())
    setup.clock.advance(timedelta(minutes=6))
    setup.portal.call(setup.altcha.verify, setup.solve())
    assert len(setup.used) == 1


def test_without_key_challenge_is_not_issued(
    portal: BlockingPortal, clock: FakeClock
) -> None:
    closed = Setup(portal, clock, None)
    with pytest.raises(RegistrationClosed):
        portal.call(closed.altcha.issue)


def test_without_key_nothing_is_accepted(
    portal: BlockingPortal, clock: FakeClock
) -> None:
    payload = Setup(portal, clock, POLICY).solve()
    closed = Setup(portal, clock, None)
    with pytest.raises(RegistrationClosed):
        portal.call(closed.altcha.verify, payload)
