"""Use cases altcha: видати задачу й перевірити розв'язок (одноразово)."""

from collections.abc import Callable

from application.ports.altcha import AltchaRandom, AltchaUnitOfWork
from application.ports.clock import Clock
from domain.identity.altcha import (
    CHALLENGE_TTL,
    REJECTED_MESSAGE,
    AltchaChallenge,
    AltchaPolicy,
    check_solution,
    make_challenge,
)
from domain.identity.errors import AltchaFailed, RegistrationClosed

CLOSED_MESSAGE = "Реєстрація закрита"


class AltchaUseCases:
    """`policy=None` — ключ не налаштовано: задач не видаємо, розв'язків не приймаємо."""

    def __init__(
        self,
        unit_of_work: Callable[[], AltchaUnitOfWork],
        clock: Clock,
        random: AltchaRandom,
        policy: AltchaPolicy | None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._random = random
        self._policy = policy

    def _open(self) -> AltchaPolicy:
        if self._policy is None:
            raise RegistrationClosed(CLOSED_MESSAGE)
        return self._policy

    async def issue(self) -> AltchaChallenge:
        policy = self._open()
        return make_challenge(
            policy,
            nonce=self._random.nonce(),
            number=self._random.number(policy.max_number),
            expires_at=self._clock.now() + CHALLENGE_TTL,
        )

    async def verify(self, payload: str) -> None:
        policy = self._open()
        now = self._clock.now()
        solution = check_solution(policy, payload, now)
        async with self._unit_of_work() as uow:
            # Прибирання під час перевірки: окремого планувальника не потрібно.
            await uow.solved_altchas.purge(now)
            if not await uow.solved_altchas.claim(
                solution.signature, solution.expires_at
            ):
                raise AltchaFailed(REJECTED_MESSAGE)
            await uow.commit()
