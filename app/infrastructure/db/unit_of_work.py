"""Unit of work на AsyncSession: одна транзакція на операцію use case.

Без `commit()` усе відкочується при виході — і при помилці, і при звичайному завершенні.
Репозиторії контекстів отримують `session` цього UoW.
"""

from collections.abc import Callable
from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from infrastructure.db.agents.repository import PostgresUserAgents
from infrastructure.db.analysis.gap_answers import PostgresGapAnswers
from infrastructure.db.analysis.repository import PostgresAnalyses
from infrastructure.db.applications.repository import PostgresApplications
from infrastructure.db.documents.downloads import PostgresDownloadLinks
from infrastructure.db.documents.repository import PostgresDocuments
from infrastructure.db.facts.repository import PostgresFacts, PostgresOriginalCvs
from infrastructure.db.identity.altcha import PostgresSolvedAltchas
from infrastructure.db.identity.invites import PostgresSignupInvites
from infrastructure.db.identity.repository import (
    PostgresExternalIdentities,
    PostgresUsers,
)
from infrastructure.db.identity.sessions import (
    PostgresLoginFailures,
    PostgresSessions,
)
from infrastructure.db.identity.signup_limits import PostgresSignupLimits
from infrastructure.db.identity.signup_requests import PostgresSignupRequests
from infrastructure.db.jobs.repository import PostgresJobs
from infrastructure.db.mail.replies import PostgresJobReplies
from infrastructure.db.mail.repository import (
    PostgresMailDropped,
    PostgresMailInboxes,
    PostgresMailMessages,
    PostgresMailSends,
    PostgresMailSync,
    PostgresMailSyncRequests,
)
from infrastructure.db.oauth.repository import (
    PostgresGrants,
    PostgresOAuthClients,
    PostgresOAuthTokens,
)
from infrastructure.db.onboarding.repository import PostgresOnboardingTips
from infrastructure.db.photos.repository import PostgresPhotos
from infrastructure.db.prep.kit_repository import PostgresInterviewKits
from infrastructure.db.prep.quiz_repository import PostgresPrepQuestions
from infrastructure.db.prep.repository import PostgresPrepTopics
from infrastructure.db.profile.repository import PostgresProfiles
from infrastructure.db.sources.repository import (
    PostgresSourceCatalog,
    PostgresSourceRefreshRequests,
    PostgresSourceRuns,
)
from infrastructure.db.triage.repository import PostgresTriage


class SqlAlchemyUnitOfWork:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions
        self._session: AsyncSession | None = None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return self._session

    async def __aenter__(self) -> Self:
        self._session = self._sessions()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session, self._session = self.session, None
        try:
            await session.rollback()
        finally:
            await session.close()

    async def commit(self) -> None:
        await self.session.commit()

    # Репозиторії контекстів — на сесії цього UoW. Новий контекст — нова властивість тут.
    @property
    def users(self) -> PostgresUsers:
        return PostgresUsers(self.session)

    @property
    def external_identities(self) -> PostgresExternalIdentities:
        return PostgresExternalIdentities(self.session)

    @property
    def solved_altchas(self) -> PostgresSolvedAltchas:
        return PostgresSolvedAltchas(self.session)

    @property
    def signup_invites(self) -> PostgresSignupInvites:
        return PostgresSignupInvites(self.session)

    @property
    def signup_limits(self) -> PostgresSignupLimits:
        return PostgresSignupLimits(self.session)

    @property
    def signup_requests(self) -> PostgresSignupRequests:
        return PostgresSignupRequests(self.session)

    @property
    def facts(self) -> PostgresFacts:
        return PostgresFacts(self.session)

    @property
    def original_cvs(self) -> PostgresOriginalCvs:
        return PostgresOriginalCvs(self.session)

    @property
    def jobs(self) -> PostgresJobs:
        return PostgresJobs(self.session)

    @property
    def applications(self) -> PostgresApplications:
        return PostgresApplications(self.session)

    @property
    def mail_inboxes(self) -> PostgresMailInboxes:
        return PostgresMailInboxes(self.session)

    @property
    def mail_messages(self) -> PostgresMailMessages:
        return PostgresMailMessages(self.session)

    @property
    def mail_dropped(self) -> PostgresMailDropped:
        return PostgresMailDropped(self.session)

    @property
    def mail_sync(self) -> PostgresMailSync:
        return PostgresMailSync(self.session)

    @property
    def mail_sync_requests(self) -> PostgresMailSyncRequests:
        return PostgresMailSyncRequests(self.session)

    @property
    def mail_sends(self) -> PostgresMailSends:
        return PostgresMailSends(self.session)

    @property
    def job_replies(self) -> PostgresJobReplies:
        return PostgresJobReplies(self.session)

    @property
    def analyses(self) -> PostgresAnalyses:
        return PostgresAnalyses(self.session)

    @property
    def gap_answers(self) -> PostgresGapAnswers:
        return PostgresGapAnswers(self.session)

    @property
    def documents(self) -> PostgresDocuments:
        return PostgresDocuments(self.session)

    @property
    def download_links(self) -> PostgresDownloadLinks:
        return PostgresDownloadLinks(self.session)

    @property
    def onboarding_tips(self) -> PostgresOnboardingTips:
        return PostgresOnboardingTips(self.session)

    @property
    def photos(self) -> PostgresPhotos:
        return PostgresPhotos(self.session)

    @property
    def triage(self) -> PostgresTriage:
        return PostgresTriage(self.session)

    @property
    def prep_topics(self) -> PostgresPrepTopics:
        return PostgresPrepTopics(self.session)

    @property
    def prep_questions(self) -> PostgresPrepQuestions:
        return PostgresPrepQuestions(self.session)

    @property
    def interview_kits(self) -> PostgresInterviewKits:
        return PostgresInterviewKits(self.session)

    @property
    def profiles(self) -> PostgresProfiles:
        return PostgresProfiles(self.session)

    @property
    def source_runs(self) -> PostgresSourceRuns:
        return PostgresSourceRuns(self.session)

    @property
    def source_refresh_requests(self) -> PostgresSourceRefreshRequests:
        return PostgresSourceRefreshRequests(self.session)

    @property
    def source_catalog(self) -> PostgresSourceCatalog:
        return PostgresSourceCatalog(self.session)

    @property
    def sessions(self) -> PostgresSessions:
        return PostgresSessions(self.session)

    @property
    def login_failures(self) -> PostgresLoginFailures:
        return PostgresLoginFailures(self.session)

    @property
    def oauth_clients(self) -> PostgresOAuthClients:
        return PostgresOAuthClients(self.session)

    @property
    def grants(self) -> PostgresGrants:
        return PostgresGrants(self.session)

    @property
    def oauth_tokens(self) -> PostgresOAuthTokens:
        return PostgresOAuthTokens(self.session)

    @property
    def user_agents(self) -> PostgresUserAgents:
        return PostgresUserAgents(self.session)


type UnitOfWorkFactory = Callable[[], SqlAlchemyUnitOfWork]


def unit_of_work_factory(engine: AsyncEngine) -> UnitOfWorkFactory:
    """Новий UoW на кожну операцію; спільні лише engine і фабрика сесій."""
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    return lambda: SqlAlchemyUnitOfWork(sessions)
