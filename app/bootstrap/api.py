"""ASGI-застосунок. Тільки фабрика — модульного `app` нема.

Запуск: `uvicorn --factory bootstrap.api:create_app`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from bootstrap.container import Container, build_container
from bootstrap.settings import Settings
from infrastructure.http.agents import agents_router
from infrastructure.http.analysis import analysis_router
from infrastructure.http.applications import applications_router
from infrastructure.http.auth import auth_router
from infrastructure.http.correlation import CorrelationIdMiddleware
from infrastructure.http.document_downloads import document_downloads_router
from infrastructure.http.documents import documents_router
from infrastructure.http.errors import install_error_handlers
from infrastructure.http.facts import facts_router
from infrastructure.http.google import google_router
from infrastructure.http.health import health_router
from infrastructure.http.jobs import jobs_router
from infrastructure.http.legal import legal_router
from infrastructure.http.mail import mail_router
from infrastructure.http.onboarding import onboarding_router
from infrastructure.http.photos import photos_router
from infrastructure.http.prep import prep_router
from infrastructure.http.profile import profile_router
from infrastructure.http.prompts import prompts_router
from infrastructure.http.replies import replies_router
from infrastructure.http.signup import signup_router
from infrastructure.http.sources import sources_router

STATE_COOKIE = "joboffer_oauth_state"
STATE_MAX_AGE = 600


def create_app(
    settings: Settings | None = None,
    *,
    google_transport: httpx2.AsyncBaseTransport | None = None,
    probe_transport: httpx2.AsyncBaseTransport | None = None,
    mail_transport: httpx2.AsyncBaseTransport | None = None,
) -> FastAPI:
    container = build_container(
        settings if settings is not None else Settings(),
        google_transport=google_transport,
        probe_transport=probe_transport,
        mail_transport=mail_transport,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await container.engine.dispose()

    app = FastAPI(
        title="joboffer",
        lifespan=lifespan,
    )
    app.state.container = container
    app.add_middleware(CorrelationIdMiddleware)
    install_error_handlers(app)
    app.include_router(health_router())
    app.include_router(legal_router(container.legal))
    app.include_router(
        auth_router(
            container.auth,
            container.altcha,
            google_enabled=container.google is not None,
        )
    )
    app.include_router(
        signup_router(container.invites, container.signup, container.auth)
    )
    app.include_router(profile_router(container.profile, container.auth))
    app.include_router(jobs_router(container.jobs, container.auth))
    app.include_router(applications_router(container.applications, container.auth))
    app.include_router(mail_router(container.mail, container.auth))
    app.include_router(replies_router(container.replies, container.auth))
    app.include_router(analysis_router(container.analysis, container.auth))
    app.include_router(facts_router(container.facts, container.auth))
    app.include_router(documents_router(container.documents, container.auth))
    app.include_router(document_downloads_router(container.document_downloads))
    app.include_router(photos_router(container.photos, container.auth))
    app.include_router(onboarding_router(container.onboarding, container.auth))
    app.include_router(agents_router(container.agents, container.auth))
    app.include_router(prompts_router(container.prompts, container.auth))
    app.include_router(
        prep_router(container.prep_web, container.interview_kits, container.auth)
    )
    app.include_router(
        sources_router(
            container.sources,
            container.source_overview,
            container.source_filtered,
            container.auth,
        )
    )
    if container.google is not None:
        # Стан OAuth-флоу (state, nonce, PKCE) — у підписаній cookie лише на час входу.
        app.add_middleware(
            SessionMiddleware,
            secret_key=container.google.config.state_secret,
            session_cookie=STATE_COOKIE,
            max_age=STATE_MAX_AGE,
            same_site="lax",
            https_only=container.settings.cookie_secure,
        )
        app.include_router(
            google_router(
                container.google,
                container.sessions,
                container.auth,
            )
        )
    return app


def container_of(app: FastAPI) -> Container:
    container = app.state.container
    if not isinstance(container, Container):
        raise TypeError("app.state.container не є Container")
    return container
