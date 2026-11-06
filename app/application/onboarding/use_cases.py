"""Use cases онбордингу: кроки з реальних даних, підказки «бачив» і «сховав»."""

from collections.abc import Callable

from application.contracts.actor import Actor
from application.contracts.onboarding import OnboardingData, StepData, TipData
from application.ports.clock import Clock
from application.ports.onboarding import OnboardingUnitOfWork
from domain.onboarding.steps import (
    OPTIONAL_STEPS,
    TIP_KEYS,
    Evidence,
    OnboardingStep,
    check_tip_key,
    completed_steps,
)


class OnboardingUseCases:
    def __init__(
        self, unit_of_work: Callable[[], OnboardingUnitOfWork], clock: Clock
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def get_onboarding(self, actor: Actor) -> OnboardingData:
        """Кроки за даними користувача (не за позначками) і підказки, які він бачив чи сховав."""
        user_id = actor.user_id
        async with self._unit_of_work() as uow:
            evidence = Evidence(
                profile=await uow.profiles.get(user_id),
                claude_connected=await uow.grants.has_live(user_id, self._clock.now()),
                has_original_cv=await uow.original_cvs.get(user_id) is not None,
                has_photo=bool(await uow.photos.all(user_id)),
                has_mail_address=await uow.mail_inboxes.find(user_id) is not None,
            )
            tips = {tip.key: tip for tip in await uow.onboarding_tips.all(user_id)}
        done = completed_steps(evidence)
        return OnboardingData(
            steps=tuple(
                StepData(
                    key=step.value,
                    done=step in done,
                    optional=step in OPTIONAL_STEPS,
                )
                for step in OnboardingStep
            ),
            tips=tuple(
                TipData(
                    key=key,
                    seen=key in tips,
                    dismissed=key in tips and tips[key].dismissed_at is not None,
                )
                for key in TIP_KEYS
            ),
            complete=all(
                step in done for step in OnboardingStep if step not in OPTIONAL_STEPS
            ),
        )

    async def mark_tip_seen(self, actor: Actor, key: str) -> None:
        """Застаріло: веб більше не показує підказки. Повтор нічого не міняє. `NotFound` — невідома підказка."""
        check_tip_key(key)
        async with self._unit_of_work() as uow:
            await uow.onboarding_tips.mark_seen(actor.user_id, key, self._clock.now())
            await uow.commit()

    async def dismiss_tip(self, actor: Actor, key: str) -> None:
        """Застаріло: веб більше не показує підказки. Ховає підказку (вона стає й баченою). Повтор нічого не міняє. `NotFound` — невідома."""
        check_tip_key(key)
        async with self._unit_of_work() as uow:
            await uow.onboarding_tips.dismiss(actor.user_id, key, self._clock.now())
            await uow.commit()
