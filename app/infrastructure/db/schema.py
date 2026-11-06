"""Повна схема адаптера: `Base.metadata` з усіма таблицями (для Alembic і тесту збігу зі схемою).

Нова таблиця контексту — імпорт її класу сюди.
"""

from infrastructure.db.agents.tables import UserAgentRow
from infrastructure.db.analysis.tables import (
    AnalysisRow,
    GapAnswerFactRow,
    GapAnswerRow,
)
from infrastructure.db.applications.tables import (
    ApplicationCvVersionRow,
    ApplicationRow,
)
from infrastructure.db.base import Base
from infrastructure.db.documents.tables import (
    DocumentCounterRow,
    DocumentDownloadLinkRow,
    DocumentRow,
)
from infrastructure.db.facts.tables import FactCounterRow, FactRow, OriginalCvRow
from infrastructure.db.identity.tables import (
    AltchaSolutionRow,
    LoginFailureRow,
    SessionRow,
    UserIdentityRow,
    UserRow,
)
from infrastructure.db.jobs.tables import JobCounterRow, JobRow
from infrastructure.db.mail.tables import (
    JobReplyRow,
    MailDroppedRow,
    MailInboxRow,
    MailMessageRow,
    MailRetiredTagRow,
    MailSendRow,
    MailSyncRequestRow,
    MailSyncStateRow,
)
from infrastructure.db.oauth.tables import OAuthClientRow, OAuthGrantRow, OAuthTokenRow
from infrastructure.db.photos.tables import PhotoCounterRow, PhotoRow
from infrastructure.db.prep.tables import (
    InterviewKitCounterRow,
    InterviewKitRow,
    PrepAnswerRow,
    PrepQuestionCounterRow,
    PrepQuestionRow,
    PrepStepCounterRow,
    PrepStepRow,
    PrepTopicCounterRow,
    PrepTopicJobRow,
    PrepTopicRow,
)
from infrastructure.db.profile.tables import ProfileLocationRow, ProfileRow
from infrastructure.db.sources.tables import (
    SourceCompanyRow,
    SourceCompanyRunRow,
    SourceFeedRow,
    SourceFeedRunRow,
)
from infrastructure.db.triage.tables import TriageRow

metadata = Base.metadata

__all__ = [
    "AltchaSolutionRow",
    "AnalysisRow",
    "ApplicationCvVersionRow",
    "ApplicationRow",
    "DocumentCounterRow",
    "DocumentDownloadLinkRow",
    "DocumentRow",
    "FactCounterRow",
    "FactRow",
    "GapAnswerFactRow",
    "GapAnswerRow",
    "InterviewKitCounterRow",
    "InterviewKitRow",
    "JobCounterRow",
    "JobReplyRow",
    "JobRow",
    "LoginFailureRow",
    "MailDroppedRow",
    "MailInboxRow",
    "MailMessageRow",
    "MailRetiredTagRow",
    "MailSendRow",
    "MailSyncRequestRow",
    "MailSyncStateRow",
    "OAuthClientRow",
    "OAuthGrantRow",
    "OAuthTokenRow",
    "OriginalCvRow",
    "PhotoCounterRow",
    "PhotoRow",
    "PrepAnswerRow",
    "PrepQuestionCounterRow",
    "PrepQuestionRow",
    "PrepStepCounterRow",
    "PrepStepRow",
    "PrepTopicCounterRow",
    "PrepTopicJobRow",
    "PrepTopicRow",
    "ProfileLocationRow",
    "ProfileRow",
    "SessionRow",
    "SourceCompanyRow",
    "SourceCompanyRunRow",
    "SourceFeedRow",
    "SourceFeedRunRow",
    "TriageRow",
    "UserAgentRow",
    "UserIdentityRow",
    "UserRow",
    "metadata",
]
