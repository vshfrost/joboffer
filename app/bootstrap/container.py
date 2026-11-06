"""Composition root: єдине місце, де конкретні реалізації з'єднуються з портами.

Контейнер тримає налаштування й ФАБРИКИ, а не спільні stateful-обʼєкти на кшталт
сесій БД: unit of work створюється заново на кожну операцію.
"""

from dataclasses import dataclass
from datetime import timedelta

import httpx2
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from application.agents.use_cases import AgentUseCases
from application.analysis.use_cases import AnalysisUseCases
from application.applications.use_cases import ApplicationUseCases
from application.documents.downloads import DocumentDownloads
from application.documents.use_cases import DocumentUseCases
from application.facts.use_cases import FactUseCases
from application.identity.altcha import AltchaUseCases
from application.identity.invites import SignupInviteUseCases
from application.identity.sessions import SessionServices, SessionUseCases
from application.identity.signup import SignupServices, SignupUseCases
from application.identity.use_cases import IdentityUseCases
from application.jobs.use_cases import JobUseCases
from application.mail.inbox import MailUseCases
from application.mail.outgoing import OutgoingMailServices, OutgoingMailUseCases
from application.mail.replies import ReplyUseCases
from application.oauth.use_cases import OAuthServices, OAuthUseCases
from application.onboarding.use_cases import OnboardingUseCases
from application.photos.use_cases import PhotoUseCases
from application.ports.clock import Clock
from application.ports.documents import DocumentOutput
from application.ports.legal import LegalDocuments
from application.ports.prompts import Prompts
from application.ports.templates import Templates
from application.prep.kit import InterviewKitUseCases
from application.prep.quiz import QuizUseCases
from application.prep.use_cases import PrepUseCases
from application.prep.web import PrepWebUseCases
from application.profile.use_cases import ProfileUseCases
from application.scenarios.prompts import ScenarioPrompts
from application.scenarios.use_cases import ScenarioUseCases
from application.sources.filtered import FilteredJobUseCases
from application.sources.manage import SourceManageUseCases
from application.sources.overview import SourceOverviewUseCases
from application.triage.use_cases import TriageUseCases
from bootstrap.settings import Settings
from domain.identity.altcha import AltchaPolicy
from domain.identity.session import SessionPolicy
from domain.identity.signup import SignupMode
from infrastructure.db.engine import create_engine
from infrastructure.db.unit_of_work import UnitOfWorkFactory, unit_of_work_factory
from infrastructure.gmail.audit import LoggingMailAudit
from infrastructure.gmail.client import GmailCredentials
from infrastructure.gmail.sender import GmailSender
from infrastructure.http.auth import CookieConfig, HttpAuth
from infrastructure.http.google import GoogleConfig, GoogleLogin
from infrastructure.legal.files import FileLegalDocuments
from infrastructure.oauth.audit import LoggingAuditLog
from infrastructure.oauth.pending import InMemoryPendingAuthorizations
from infrastructure.oauth.redirect import RedirectAllowlist
from infrastructure.pdf.files import FileDocuments
from infrastructure.pdf.inspector import PypdfInspector
from infrastructure.pdf.pdftotext import PdftotextReader
from infrastructure.pdf.render import WeasyPrintRenderer
from infrastructure.photos.pillow import PillowPhotos
from infrastructure.prompts.catalog import FilePrompts
from infrastructure.security.passwords import Argon2PasswordHasher
from infrastructure.sources.probe import AtsProbe
from infrastructure.system import (
    RandomAltcha,
    RandomCodes,
    RandomIds,
    RandomTokens,
    SystemClock,
)
from infrastructure.templates.catalog import FileTemplates


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    # Пул з'єднань — один на застосунок; закривається в lifespan (bootstrap.api).
    engine: AsyncEngine
    unit_of_work: UnitOfWorkFactory
    identity: IdentityUseCases
    sessions: SessionUseCases
    invites: SignupInviteUseCases
    signup: SignupUseCases
    auth: HttpAuth
    altcha: AltchaUseCases
    prompts: Prompts
    templates: Templates
    legal: LegalDocuments
    oauth: OAuthUseCases
    profile: ProfileUseCases
    jobs: JobUseCases
    applications: ApplicationUseCases
    mail: MailUseCases
    replies: ReplyUseCases
    facts: FactUseCases
    triage: TriageUseCases
    analysis: AnalysisUseCases
    scenarios: ScenarioUseCases
    prep: PrepUseCases
    prep_web: PrepWebUseCases
    quiz: QuizUseCases
    interview_kits: InterviewKitUseCases
    documents: DocumentUseCases
    document_downloads: DocumentDownloads
    photos: PhotoUseCases
    onboarding: OnboardingUseCases
    agents: AgentUseCases
    sources: SourceManageUseCases
    source_overview: SourceOverviewUseCases
    source_filtered: FilteredJobUseCases
    # Реєстрація відкрита лише коли є чим відправити лист; без токена gmail.send — закрита.
    registration_open: bool
    outgoing_mail: OutgoingMailUseCases | None
    # None — Google не налаштовано: кнопки нема, пароль працює.
    google: GoogleLogin | None
    # Той самий клієнт Google, але з адресою повернення логін-гейта MCP.
    google_gate: GoogleLogin | None


def build_container(
    settings: Settings,
    *,
    google_transport: httpx2.AsyncBaseTransport | None = None,
    probe_transport: httpx2.AsyncBaseTransport | None = None,
    mail_transport: httpx2.AsyncBaseTransport | None = None,
) -> Container:
    # Engine лінивий: з'єднання відкриваються при першому запиті, не тут.
    engine = create_engine(settings.database_url.get_secret_value())
    unit_of_work = unit_of_work_factory(engine)
    clock, ids = SystemClock(), RandomIds()
    prompts = ScenarioPrompts(FilePrompts.load(settings.prompts_dir))
    templates = FileTemplates.load(settings.templates_dir)
    prep = PrepUseCases(unit_of_work, clock, ids, prompts)
    jobs = JobUseCases(unit_of_work, clock, ids)
    analysis = AnalysisUseCases(unit_of_work, clock, ids, prompts)
    hasher = Argon2PasswordHasher()
    identity = IdentityUseCases(unit_of_work, clock, ids, hasher)
    policy = SessionPolicy(
        idle=timedelta(hours=settings.session_idle_hours),
        absolute=timedelta(days=settings.session_absolute_days),
    )
    sessions = SessionUseCases(
        unit_of_work,
        identity,
        SessionServices(clock=clock, ids=ids, tokens=RandomTokens(), policy=policy),
    )
    altcha = AltchaUseCases(
        unit_of_work,
        clock,
        RandomAltcha(),
        None
        if settings.altcha_hmac_key is None
        else AltchaPolicy(
            settings.altcha_hmac_key.get_secret_value(), settings.altcha_maxnumber
        ),
    )
    signup_mode = SignupMode(settings.signup_mode)
    invites = SignupInviteUseCases(
        unit_of_work, clock, ids, RandomTokens(), signup_mode
    )
    legal = FileLegalDocuments.load(settings.templates_dir)
    outgoing_mail = _outgoing_mail(
        settings, unit_of_work, clock, templates, mail_transport
    )
    cookie = CookieConfig(
        name=settings.session_cookie,
        secure=settings.cookie_secure,
        max_age=int(policy.absolute.total_seconds()),
    )
    return Container(
        settings=settings,
        engine=engine,
        unit_of_work=unit_of_work,
        identity=identity,
        sessions=sessions,
        altcha=altcha,
        invites=invites,
        signup=SignupUseCases(
            unit_of_work,
            SignupServices(
                clock=clock,
                ids=ids,
                hasher=hasher,
                codes=RandomCodes(),
                altcha=altcha,
                invites=invites,
                legal=legal,
                sessions=sessions,
                mail=outgoing_mail,
                mode=signup_mode,
            ),
        ),
        auth=HttpAuth(
            sessions,
            cookie,
            settings.trusted_proxies,
            client_ip_header=settings.client_ip_header,
        ),
        prompts=prompts,
        templates=templates,
        registration_open=settings.mail_sending_enabled,
        outgoing_mail=outgoing_mail,
        legal=legal,
        google=_google(settings, google_transport),
        google_gate=_google(settings, google_transport, gate=True),
        profile=ProfileUseCases(unit_of_work, clock),
        jobs=jobs,
        applications=ApplicationUseCases(unit_of_work, clock),
        mail=MailUseCases(unit_of_work, clock, settings.mail_address),
        replies=ReplyUseCases(unit_of_work, clock),
        facts=FactUseCases(unit_of_work, clock, ids),
        triage=TriageUseCases(unit_of_work, clock, ids, prompts),
        analysis=analysis,
        scenarios=ScenarioUseCases(jobs, analysis, prompts),
        prep=prep,
        prep_web=PrepWebUseCases(unit_of_work, clock, prep),
        quiz=QuizUseCases(unit_of_work, clock, ids, prompts),
        interview_kits=InterviewKitUseCases(unit_of_work, clock, ids, prompts),
        documents=DocumentUseCases(
            unit_of_work,
            clock,
            ids,
            prompts,
            DocumentOutput(
                WeasyPrintRenderer(templates),
                PypdfInspector(PdftotextReader()),
                FileDocuments(settings.documents_dir),
            ),
        ),
        document_downloads=DocumentDownloads(
            unit_of_work,
            clock,
            RandomTokens(),
            FileDocuments(settings.documents_dir),
        ),
        photos=PhotoUseCases(unit_of_work, PillowPhotos(), clock, ids),
        onboarding=OnboardingUseCases(unit_of_work, clock),
        agents=AgentUseCases(unit_of_work, clock),
        sources=SourceManageUseCases(unit_of_work, AtsProbe(probe_transport), ids),
        source_overview=SourceOverviewUseCases(unit_of_work, clock),
        source_filtered=FilteredJobUseCases(unit_of_work, clock),
        oauth=OAuthUseCases(
            unit_of_work,
            InMemoryPendingAuthorizations(),
            OAuthServices(
                clock=clock,
                ids=ids,
                tokens=RandomTokens(),
                resource=settings.agent_public_url,
                allowlist=RedirectAllowlist(settings.agent_redirect_allowlist),
                audit=LoggingAuditLog(),
            ),
        ),
    )


def _google(
    settings: Settings,
    transport: httpx2.AsyncBaseTransport | None,
    *,
    gate: bool = False,
) -> GoogleLogin | None:
    redirect = (
        settings.google_gate_redirect_uri if gate else settings.google_redirect_uri
    )
    if not settings.google_enabled or redirect is None:
        return None
    return GoogleLogin(
        GoogleConfig(
            client_id=str(settings.google_client_id),
            client_secret=_reveal(settings.google_client_secret),
            redirect_uri=redirect,
            metadata_url=settings.google_metadata_url,
            state_secret=_reveal(settings.auth_state_secret),
        ),
        transport=transport,
    )


def _outgoing_mail(
    settings: Settings,
    unit_of_work: UnitOfWorkFactory,
    clock: Clock,
    templates: Templates,
    transport: httpx2.AsyncBaseTransport | None,
) -> OutgoingMailUseCases | None:
    if not settings.mail_sending_enabled:
        return None
    creds = GmailCredentials(
        client_id=str(settings.gmail_client_id),
        client_secret=_reveal(settings.gmail_client_secret),
        refresh_token=_reveal(settings.gmail_send_refresh_token),
    )
    return OutgoingMailUseCases(
        unit_of_work,
        clock,
        OutgoingMailServices(
            sender=GmailSender(creds, settings.mail_address, transport),
            templates=templates,
            audit=LoggingMailAudit(),
            daily_limit=settings.mail_send_daily_limit,
        ),
    )


def _reveal(secret: SecretStr | None) -> str:
    return "" if secret is None else secret.get_secret_value()
