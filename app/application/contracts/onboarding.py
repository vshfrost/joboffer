"""Результати контексту onboarding: примітиви."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class StepData:
    key: str
    done: bool
    optional: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class TipData:
    key: str
    seen: bool
    dismissed: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class OnboardingData:
    steps: tuple[StepData, ...]
    tips: tuple[TipData, ...]
    # Усі обов'язкові кроки зроблено.
    complete: bool
