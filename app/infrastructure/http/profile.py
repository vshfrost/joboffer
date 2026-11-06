"""HTTP профілю: читання цілком і збереження по розділах.

Тіла розділів — рядки й списки без enum-ів: невідомий рівень чи формат відхиляє домен зі
своїм текстом (v1), а не pydantic. Збереження повертає профіль цілком.
"""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict

from application.contracts.actor import Actor
from application.contracts.profile import (
    ContactsData,
    LocationData,
    LocationsData,
    ProfileData,
    RulesData,
    TargetData,
)
from application.profile.use_cases import ProfileUseCases
from infrastructure.http.auth import HttpAuth


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TargetModel(_Body):
    roles: list[str]
    seniority: list[str]
    min_salary_eur: int | None
    target_domains: list[str]


class LocationModel(_Body):
    place: str
    aliases: list[str]
    work_modes: list[str]


class LocationsModel(_Body):
    work_modes: list[str]
    locations: list[LocationModel]
    include_unknown_mode: bool
    relocation: bool


class RulesModel(_Body):
    title_keywords: list[str]
    title_exclude: list[str]
    stop_words: list[str]


class ContactsModel(_Body):
    full_name: str
    email: str
    phone: str
    linkedin_url: str
    city: str
    github_url: str
    work_authorization: str


class ProfileModel(BaseModel):
    target: TargetModel
    locations: LocationsModel
    rules: RulesModel
    contacts: ContactsModel


def _model(data: ProfileData) -> ProfileModel:
    return ProfileModel(
        target=TargetModel(
            roles=list(data.target.roles),
            seniority=list(data.target.seniority),
            min_salary_eur=data.target.min_salary_eur,
            target_domains=list(data.target.target_domains),
        ),
        locations=LocationsModel(
            work_modes=list(data.locations.work_modes),
            locations=[
                LocationModel(
                    place=item.place,
                    aliases=list(item.aliases),
                    work_modes=list(item.work_modes),
                )
                for item in data.locations.locations
            ],
            include_unknown_mode=data.locations.include_unknown_mode,
            relocation=data.locations.relocation,
        ),
        rules=RulesModel(
            title_keywords=list(data.rules.title_keywords),
            title_exclude=list(data.rules.title_exclude),
            stop_words=list(data.rules.stop_words),
        ),
        contacts=ContactsModel(**asdict(data.contacts)),
    )


def profile_router(profiles: ProfileUseCases, auth: HttpAuth) -> APIRouter:
    router = APIRouter(prefix="/profile", tags=["profile"])
    current = Depends(auth.actor)
    Caller = Annotated[Actor, current]

    def private(response: Response) -> None:
        response.headers["Cache-Control"] = "no-store"

    @router.get("")
    async def read(actor: Caller, response: Response) -> ProfileModel:
        private(response)
        return _model(await profiles.get_profile(actor))

    @router.put("/target")
    async def save_target(
        body: TargetModel, actor: Caller, response: Response
    ) -> ProfileModel:
        private(response)
        data = TargetData(
            roles=tuple(body.roles),
            seniority=tuple(body.seniority),
            min_salary_eur=body.min_salary_eur,
            target_domains=tuple(body.target_domains),
        )
        return _model(await profiles.save_section(actor, data))

    @router.put("/locations")
    async def save_locations(
        body: LocationsModel, actor: Caller, response: Response
    ) -> ProfileModel:
        private(response)
        data = LocationsData(
            work_modes=tuple(body.work_modes),
            locations=tuple(
                LocationData(
                    place=item.place,
                    aliases=tuple(item.aliases),
                    work_modes=tuple(item.work_modes),
                )
                for item in body.locations
            ),
            include_unknown_mode=body.include_unknown_mode,
            relocation=body.relocation,
        )
        return _model(await profiles.save_section(actor, data))

    @router.put("/rules")
    async def save_rules(
        body: RulesModel, actor: Caller, response: Response
    ) -> ProfileModel:
        private(response)
        data = RulesData(
            title_keywords=tuple(body.title_keywords),
            title_exclude=tuple(body.title_exclude),
            stop_words=tuple(body.stop_words),
        )
        return _model(await profiles.save_section(actor, data))

    @router.put("/contacts")
    async def save_contacts(
        body: ContactsModel, actor: Caller, response: Response
    ) -> ProfileModel:
        private(response)
        return _model(
            await profiles.save_section(actor, ContactsData(**body.model_dump()))
        )

    return router
