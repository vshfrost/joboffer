"""Адаптери джерел вакансій: кожен реалізує `JobSource` і читає лише мережу."""

from application.ports.job_sources import JobSource
from domain.sources.kinds import FeedSource, Platform, SourceKind
from infrastructure.sources.ashby import AshbySource
from infrastructure.sources.djinni import DjinniSource
from infrastructure.sources.dou import DouSource
from infrastructure.sources.greenhouse import GreenhouseSource
from infrastructure.sources.http import Fetcher
from infrastructure.sources.lever import LeverSource


def build_sources(fetcher: Fetcher) -> dict[SourceKind, JobSource]:
    """Адаптери за видом джерела."""
    return {
        Platform.GREENHOUSE: GreenhouseSource(fetcher),
        Platform.ASHBY: AshbySource(fetcher),
        Platform.LEVER: LeverSource(fetcher),
        FeedSource.DOU: DouSource(fetcher),
        FeedSource.DJINNI: DjinniSource(fetcher),
    }
