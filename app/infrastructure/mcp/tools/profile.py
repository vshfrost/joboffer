"""Тули профілю: `get_profile` і `update_profile`. Контракт (назви, поля, enum-и) — як у v1.

Значення enum-ів — у JSON-схемі тулів, щоб Claude бачив допустимі варіанти; рядки поза схемою
відхиляє SDK, решту (дублі, ліміти, формати) — домен зі своїми текстами.
"""

from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from application.contracts.profile import (
    ContactsData,
    LocationData,
    LocationsData,
    ProfileData,
    RulesData,
    TargetData,
)
from application.ports.prompts import PromptKey, Prompts
from application.profile.use_cases import ProfileUseCases
from domain.shared.errors import DomainError
from infrastructure.mcp.actor import current_actor
from infrastructure.mcp.annotations import READ, WRITE

WorkModeName = Literal["remote", "hybrid", "onsite"]
SeniorityName = Literal["junior", "middle", "senior", "lead", "principal"]


class SearchLocationView(BaseModel):
    """Where to search: a posting passes if its location contains the place or a synonym and its work mode is one of work_modes."""

    place: str = Field(description="City, country or region, e.g. Valencia")
    aliases: list[str] = Field(
        default_factory=list,
        description="Other spellings and languages of the place, e.g. Валенсія; a synonym also matches as the start of a word",
    )
    work_modes: list[WorkModeName] = Field(
        min_length=1, description="Work modes accepted at this place"
    )


class Profile(BaseModel):
    """What job the user is looking for and their contacts for the CV header. Empty lists, strings and null: no restriction / not set."""

    roles: list[str] = Field(default_factory=list)
    work_modes: list[WorkModeName] = Field(default_factory=list)
    locations: list[SearchLocationView] = Field(
        default_factory=list,
        description="Where job sources are searched (empty: anywhere)",
    )
    include_unknown_mode: bool = Field(
        default=True,
        description="A source posting with no stated work mode: true — a matching place is enough, false — skip it",
    )
    relocation: bool = False
    target_domains: list[str] = Field(
        default_factory=list,
        description="Industries the job search targets, e.g. fintech, payments: examples for the domain-fit part of the analysis rubric",
    )
    seniority: list[SeniorityName] = Field(default_factory=list)
    min_salary_eur: int | None = Field(default=None, description="Gross per year, EUR")
    stop_words: list[str] = Field(default_factory=list)
    title_keywords: list[str] = Field(
        default_factory=list,
        description="Job sources import a posting only if its title contains one of these words (empty: any title)",
    )
    title_exclude: list[str] = Field(
        default_factory=list,
        description="Job sources skip a posting whose title contains one of these words",
    )
    full_name: str = Field(default="", description="CV header")
    email: str = Field(default="", description="CV header")
    phone: str = Field(default="", description="CV header, international format")
    linkedin_url: str = Field(default="", description="CV header, https://…")
    city: str = Field(default="", description="CV header, e.g. Valencia, Spain")
    github_url: str = Field(default="", description="CV header, https://…")
    work_authorization: str = Field(
        default="", description="CV header, e.g. Spain / EU work authorization"
    )


def profile_view(data: ProfileData) -> Profile:
    return Profile(
        roles=list(data.target.roles),
        work_modes=list(data.locations.work_modes),
        locations=[
            SearchLocationView(
                place=item.place,
                aliases=list(item.aliases),
                work_modes=list(item.work_modes),
            )
            for item in data.locations.locations
        ],
        include_unknown_mode=data.locations.include_unknown_mode,
        relocation=data.locations.relocation,
        target_domains=list(data.target.target_domains),
        seniority=list(data.target.seniority),
        min_salary_eur=data.target.min_salary_eur,
        stop_words=list(data.rules.stop_words),
        title_keywords=list(data.rules.title_keywords),
        title_exclude=list(data.rules.title_exclude),
        full_name=data.contacts.full_name,
        email=data.contacts.email,
        phone=data.contacts.phone,
        linkedin_url=data.contacts.linkedin_url,
        city=data.contacts.city,
        github_url=data.contacts.github_url,
        work_authorization=data.contacts.work_authorization,
    )


def _data(profile: Profile) -> ProfileData:
    return ProfileData(
        target=TargetData(
            roles=tuple(profile.roles),
            seniority=tuple(profile.seniority),
            min_salary_eur=profile.min_salary_eur,
            target_domains=tuple(profile.target_domains),
        ),
        locations=LocationsData(
            work_modes=tuple(profile.work_modes),
            locations=tuple(
                LocationData(
                    place=item.place,
                    aliases=tuple(item.aliases),
                    work_modes=tuple(item.work_modes),
                )
                for item in profile.locations
            ),
            include_unknown_mode=profile.include_unknown_mode,
            relocation=profile.relocation,
        ),
        rules=RulesData(
            title_keywords=tuple(profile.title_keywords),
            title_exclude=tuple(profile.title_exclude),
            stop_words=tuple(profile.stop_words),
        ),
        contacts=ContactsData(
            full_name=profile.full_name,
            email=profile.email,
            phone=profile.phone,
            linkedin_url=profile.linkedin_url,
            city=profile.city,
            github_url=profile.github_url,
            work_authorization=profile.work_authorization,
        ),
    )


def register_profile_tools(
    agent: MCPServer, profiles: ProfileUseCases, prompts: Prompts
) -> None:
    @agent.tool(
        name="get_profile",
        description=prompts.get(PromptKey.MCP_TOOL_GET_PROFILE),
        annotations=READ,
    )
    async def get_profile() -> Profile:
        return profile_view(await profiles.get_profile(current_actor()))

    @agent.tool(
        name="update_profile",
        description=prompts.get(PromptKey.MCP_TOOL_UPDATE_PROFILE),
        annotations=WRITE,
    )
    async def update_profile(profile: Profile) -> Profile:
        try:
            saved = await profiles.replace_profile(current_actor(), _data(profile))
        except DomainError as error:
            raise ToolError(error.message) from error
        return profile_view(saved)
