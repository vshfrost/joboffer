"""Запуск тріажу за правилами: один прохід, лог лише з лічильників і кодів помилок (без вмісту
вакансій), `--report` лише читає, складання в `main`."""

import logging
from datetime import UTC, datetime
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal

from application.triage.auto import AutoTriageUseCases
from bootstrap import auto_triage
from domain.analysis.analysis import Analysis, JobAnalysis
from domain.facts.fact import Fact, FactKind
from domain.facts.ids import FactId
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from domain.profile.profile import Profile
from domain.profile.rules import Rules
from domain.triage.triage import Triage, TriageVerdict
from tests.support.clock import FakeClock
from tests.support.core_conftest import portal
from tests.support.facts import Store as FactStore
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork, Store
from tests.support.triage import AutoRun, InMemoryAutoTriageUnitOfWork

__all__ = ["portal"]

DUMMY_URL = "postgresql+psycopg://joboffer@localhost:1/joboffer"
NOW = datetime(2026, 11, 4, 8, 30, tzinfo=UTC)
TARAS = UserId(UUID(int=101))
KATYA = UserId(UUID(int=102))
SECRET = "Secret Globex confidential payroll"


@pytest.fixture(autouse=True)
def _environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBOFFER_DATABASE_URL", DUMMY_URL)


@pytest.fixture
def audit_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> pytest.LogCaptureFixture:
    """Логер доступний для caplog: попередні тести (import-linter) налаштовують logging
    через dictConfig і вимикають вже створені логери."""
    for name in ("joboffer", "joboffer.triage"):
        logger = logging.getLogger(name)
        monkeypatch.setattr(logger, "disabled", False)
        monkeypatch.setattr(logger, "propagate", True)
    caplog.set_level(logging.INFO, logger="joboffer.triage")
    return caplog


class Run:
    def __init__(self, portal: BlockingPortal) -> None:
        self.portal = portal
        self.store = Store.empty()
        self.state = AutoRun()
        self.profiles: dict[UserId, Profile] = {}
        self.facts = FactStore.empty()
        self.ids = SequentialIds(500)

    def seed(
        self,
        user: UserId,
        text: str = f"Great job. {SECRET}",
        location: str | None = None,
    ) -> int:
        async def add() -> int:
            async with InMemoryJobUnitOfWork(self.store) as uow:
                number = await uow.jobs.add(
                    user,
                    JobId(self.ids.new()),
                    NewJob(text=text, title=SECRET, company=SECRET, location=location),
                    NOW,
                )
                await uow.commit()
                return number

        return self.portal.call(add)

    def confirm(self, user: UserId, *texts: str) -> None:
        for text in texts:
            number = 1 + sum(1 for owner, _ in self.facts.facts if owner == user)
            self.facts.facts[(user, number)] = Fact(
                FactId(self.ids.new()),
                number,
                FactKind.SKILL,
                text,
                True,
                NOW,
                NOW,
            )

    def unit_of_work(self) -> InMemoryAutoTriageUnitOfWork:
        return InMemoryAutoTriageUnitOfWork(
            self.store, self.profiles, self.facts, self.state
        )

    def use_cases(self) -> AutoTriageUseCases:
        return AutoTriageUseCases(self.unit_of_work, FakeClock(NOW), SequentialIds(900))


def test_run_logs_counts_without_vacancy_content(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    run = Run(portal)
    run.seed(TARAS)
    run.seed(KATYA)

    code = portal.call(auto_triage.run_auto_triage, run.use_cases())

    assert code == 0
    assert (
        "AUTO_TRIAGE run done: users=2 triaged=2 failed=0 analyse=0 maybe=2 skip=0"
        in audit_log.text
    )
    assert len(run.store.triage) == 2
    for secret in ("Secret", "Globex", "payroll", "Great job"):
        assert secret not in audit_log.text


def test_a_failing_user_is_logged_by_error_code_and_does_not_fail_the_run(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    run = Run(portal)
    run.seed(TARAS)
    run.seed(KATYA)
    run.state.failing = {TARAS}

    code = portal.call(auto_triage.run_auto_triage, run.use_cases())

    assert code == 0
    assert f"AUTO_TRIAGE user={TARAS} error=RuntimeError" in audit_log.text
    assert (
        "AUTO_TRIAGE run done: users=2 triaged=1 failed=1 analyse=0 maybe=1 skip=0"
        in audit_log.text
    )
    assert "Збій бази" not in audit_log.text


def test_run_skips_while_another_run_holds_the_lock(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    run = Run(portal)
    run.seed(TARAS)
    run.state.locked = True

    code = portal.call(auto_triage.run_auto_triage, run.use_cases())

    assert code == 0
    assert "AUTO_TRIAGE run skipped" in audit_log.text
    assert run.store.triage == {}


def test_run_with_nothing_to_do_is_done_with_zero_counts(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    code = portal.call(auto_triage.run_auto_triage, Run(portal).use_cases())

    assert code == 0
    assert (
        "AUTO_TRIAGE run done: users=0 triaged=0 failed=0 analyse=0 maybe=0 skip=0"
        in audit_log.text
    )


def test_report_logs_the_comparison_and_the_pending_distribution_and_writes_nothing(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    run = Run(portal)
    close = run.seed(TARAS)
    far = run.seed(TARAS)
    run.seed(TARAS)
    run.store.analyses[(TARAS, close)] = Analysis(
        close, JobAnalysis(score=36, summary="S."), (), NOW
    )
    run.store.analyses[(TARAS, far)] = Analysis(
        far, JobAnalysis(score=70, summary="S."), (), NOW
    )

    code = portal.call(auto_triage.run_report, run.use_cases())

    assert code == 0
    assert (
        "AUTO_TRIAGE report: users=1 compared=2 mean_gap=-3.0 mean_abs_gap=17.0"
        " agreed=0 analyse=0 maybe=2 skip=0" in audit_log.text
    )
    assert (
        "AUTO_TRIAGE report pending: total=1 analyse=0 maybe=1 skip=0" in audit_log.text
    )
    assert run.store.triage == {}
    for secret in ("Secret", "Globex", "payroll", "Great job"):
        assert secret not in audit_log.text


def detail_run(portal: BlockingPortal) -> Run:
    run = Run(portal)
    close = run.seed(TARAS)
    far = run.seed(TARAS)
    run.seed(TARAS)
    run.store.analyses[(TARAS, close)] = Analysis(
        close, JobAnalysis(score=36, summary="S."), (), NOW
    )
    run.store.analyses[(TARAS, far)] = Analysis(
        far, JobAnalysis(score=70, summary="S."), (), NOW
    )
    return run


def test_detail_prints_one_line_per_compared_job_with_the_breakdown(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    run = detail_run(portal)

    code = portal.call(auto_triage.run_report, run.use_cases(), True)

    assert code == 0
    assert (
        "AUTO_TRIAGE detail job=1 rules=50 analysis=36 gap=+14 rules_verdict=maybe"
        " analysis_verdict=skip agreed=no must=20 role_level=20 format_location=8"
        " domain=0 nice=0 salary=2 must_req=0/0 nice_req=0/0 mismatches=none"
        in audit_log.text
    )
    assert (
        "AUTO_TRIAGE detail job=2 rules=50 analysis=70 gap=-20 rules_verdict=maybe"
        " analysis_verdict=analyse agreed=no must=20 role_level=20 format_location=8"
        " domain=0 nice=0 salary=2 must_req=0/0 nice_req=0/0 mismatches=none"
        in audit_log.text
    )
    assert "detail job=3" not in audit_log.text


def test_detail_ends_with_the_mean_gap_and_the_mean_rules_points_per_component(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    run = detail_run(portal)

    portal.call(auto_triage.run_report, run.use_cases(), True)

    assert (
        "AUTO_TRIAGE detail summary: compared=2 mean_gap=-3.0 rules_mean_must=20.0"
        " rules_mean_role_level=20.0 rules_mean_format_location=8.0"
        " rules_mean_domain=0.0 rules_mean_nice=0.0 rules_mean_salary=2.0"
        in audit_log.text
    )


def test_detail_with_nothing_to_compare_has_a_zero_summary(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    portal.call(auto_triage.run_report, Run(portal).use_cases(), True)

    assert (
        "AUTO_TRIAGE detail summary: compared=0 mean_gap=+0.0 rules_mean_must=0.0"
        " rules_mean_role_level=0.0 rules_mean_format_location=0.0"
        " rules_mean_domain=0.0 rules_mean_nice=0.0 rules_mean_salary=0.0"
        in audit_log.text
    )


def detail_line(
    portal: BlockingPortal,
    audit_log: pytest.LogCaptureFixture,
    text: str,
    location: str | None,
) -> str:
    run = Run(portal)
    number = run.seed(TARAS, text, location)
    run.store.analyses[(TARAS, number)] = Analysis(
        number, JobAnalysis(score=70, summary="S."), (), NOW
    )
    portal.call(auto_triage.run_report, run.use_cases(), True)
    (line,) = [m for m in audit_log.messages if m.startswith("AUTO_TRIAGE detail job=")]
    return line


@pytest.mark.parametrize(
    ("text", "location", "flags"),
    [
        ("Great job.", None, "location=unknown mode=unknown"),
        ("Great job.", "Atlantis", "location=known mode=unknown"),
        ("Remote position.", None, "location=unknown mode=known"),
        ("Great job.", "Atlantis, Remote", "location=known mode=known"),
    ],
)
def test_detail_says_whether_the_location_and_the_work_mode_are_known(
    portal: BlockingPortal,
    audit_log: pytest.LogCaptureFixture,
    text: str,
    location: str | None,
    flags: str,
) -> None:
    line = detail_line(portal, audit_log, text, location)

    assert line.endswith(f" mismatches=none {flags}")


def test_detail_shows_only_the_known_flags_for_a_location_never_its_text(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    line = detail_line(portal, audit_log, "Great job.", "Atlantis, Remote")

    assert "Atlantis" not in line
    assert "Atlantis" not in audit_log.text


def test_detail_names_the_fired_mismatches(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    run = Run(portal)
    number = run.seed(TARAS)
    run.profiles[TARAS] = Profile(rules=Rules(stop_words=("payroll",)))
    run.store.analyses[(TARAS, number)] = Analysis(
        number, JobAnalysis(score=36, summary="S."), (), NOW
    )

    portal.call(auto_triage.run_report, run.use_cases(), True)

    assert "mismatches=stop_word" in audit_log.text


def test_detail_leaks_no_job_fields_and_writes_nothing(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    run = detail_run(portal)

    portal.call(auto_triage.run_report, run.use_cases(), True)

    assert "AUTO_TRIAGE detail job=1" in audit_log.text
    assert "AUTO_TRIAGE detail pending band_from=50" in audit_log.text
    assert "AUTO_TRIAGE detail pending lowest_analyse=none" in audit_log.text
    for secret in ("Secret", "Globex", "confidential", "payroll", "Great job"):
        assert secret not in audit_log.text
    assert run.store.triage == {}


PENDING_TEXT = "Requirements:\nPython\nDocker\nKafka"


def pending_run(portal: BlockingPortal) -> Run:
    """Черга користувача: два analyse (70 і 77), maybe 50, два skip (50 і 70) за стоп-словом."""
    run = Run(portal)
    run.confirm(TARAS, "Python", "Docker", "Kafka")
    run.profiles[TARAS] = Profile(rules=Rules(stop_words=("blockchain",)))
    run.seed(TARAS, PENDING_TEXT)
    run.seed(TARAS, f"{PENDING_TEXT}\nRemote.")
    run.seed(TARAS, f"Great job. {SECRET}")
    run.seed(TARAS, f"Great job. blockchain {SECRET}")
    run.seed(TARAS, f"{PENDING_TEXT}\nblockchain")
    return run


def detail_pending(audit_log: pytest.LogCaptureFixture) -> list[str]:
    return [
        message.removeprefix("AUTO_TRIAGE detail pending ")
        for message in audit_log.messages
        if message.startswith("AUTO_TRIAGE detail pending ")
    ]


def test_detail_counts_the_pending_queue_per_five_point_band_split_by_verdict(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    portal.call(auto_triage.run_report, pending_run(portal).use_cases(), True)

    bands = [line for line in detail_pending(audit_log) if line.startswith("band_from")]
    assert bands == [
        "band_from=50 analyse=0 maybe=1 skip=1",
        "band_from=70 analyse=1 maybe=0 skip=1",
        "band_from=75 analyse=1 maybe=0 skip=0",
    ]


def test_detail_lists_the_lowest_pending_analyse_and_the_highest_pending_skip(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    portal.call(auto_triage.run_report, pending_run(portal).use_cases(), True)

    assert detail_pending(audit_log)[-2:] == [
        "lowest_analyse=1:70,2:77",
        "highest_skip=5:70,4:50",
    ]


def test_detail_lists_at_most_ten_jobs_ordered_by_score_then_number(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    run = Run(portal)
    run.confirm(TARAS, "Python", "Docker", "Kafka")
    run.profiles[TARAS] = Profile(rules=Rules(stop_words=("blockchain",)))
    for _ in range(11):
        run.seed(TARAS, PENDING_TEXT)
    run.seed(TARAS, f"{PENDING_TEXT}\nRemote.")
    for _ in range(11):
        run.seed(TARAS, f"{PENDING_TEXT}\nblockchain")
    run.seed(TARAS, f"{PENDING_TEXT}\nblockchain Remote.")

    portal.call(auto_triage.run_report, run.use_cases(), True)

    lowest, highest = detail_pending(audit_log)[-2:]
    assert lowest == "lowest_analyse=" + ",".join(f"{n}:70" for n in range(1, 11))
    assert highest == "highest_skip=24:77," + ",".join(f"{n}:70" for n in range(13, 22))


def test_detail_with_an_empty_queue_prints_none(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    portal.call(auto_triage.run_report, Run(portal).use_cases(), True)

    assert detail_pending(audit_log) == [
        "bands=none",
        "lowest_analyse=none",
        "highest_skip=none",
    ]


def test_detail_pending_lines_come_after_the_per_job_lines_and_hold_no_vacancy_content(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    run = pending_run(portal)
    run.seed(KATYA, "Great job at Atlantis", "Atlantis")

    portal.call(auto_triage.run_report, run.use_cases(), True)

    messages = audit_log.messages
    summary = next(i for i, m in enumerate(messages) if "detail summary" in m)
    first = next(i for i, m in enumerate(messages) if "detail pending" in m)
    assert first > summary
    for line in detail_pending(audit_log):
        assert all(ch in "0123456789:,=_abcdefghijklmnopqrstuvwxyz " for ch in line)
    for secret in (
        "Secret",
        "Globex",
        "payroll",
        "Great job",
        "Atlantis",
        "blockchain",
    ):
        assert secret not in audit_log.text
    assert run.store.triage == {}


def test_report_without_detail_prints_no_detail_lines(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    portal.call(auto_triage.run_report, detail_run(portal).use_cases())

    assert "AUTO_TRIAGE report:" in audit_log.text
    assert "AUTO_TRIAGE detail" not in audit_log.text


class FakeEngine:
    disposed = False

    async def dispose(self) -> None:
        self.disposed = True


@pytest.fixture
def main_env(
    monkeypatch: pytest.MonkeyPatch, portal: BlockingPortal
) -> tuple[Run, FakeEngine]:
    """`main()` без бази: engine і сховище підмінені."""
    run, engine = Run(portal), FakeEngine()
    monkeypatch.setattr(auto_triage, "create_engine", lambda url: engine)
    monkeypatch.setattr(
        auto_triage, "unit_of_work_factory", lambda _engine: run.unit_of_work
    )
    return run, engine


def test_main_triages_once_and_releases_the_engine(
    main_env: tuple[Run, FakeEngine],
) -> None:
    run, engine = main_env
    number = run.seed(TARAS)

    code = auto_triage.main([])

    assert code == 0
    saved = run.store.triage.get((TARAS, number))
    assert isinstance(saved, Triage)
    assert saved.verdict is TriageVerdict.MAYBE
    assert engine.disposed


def test_main_with_report_reads_only(main_env: tuple[Run, FakeEngine]) -> None:
    run, engine = main_env
    run.seed(TARAS)

    code = auto_triage.main(["--report"])

    assert code == 0
    assert run.store.triage == {}
    assert engine.disposed


def test_main_with_report_and_detail_reads_only(
    main_env: tuple[Run, FakeEngine], audit_log: pytest.LogCaptureFixture
) -> None:
    run, engine = main_env
    run.seed(TARAS)

    code = auto_triage.main(["--report", "--detail"])

    assert code == 0
    assert "AUTO_TRIAGE detail summary: compared=0" in audit_log.text
    assert run.store.triage == {}
    assert engine.disposed


def test_main_rejects_detail_without_report(
    main_env: tuple[Run, FakeEngine], capsys: pytest.CaptureFixture[str]
) -> None:
    run, engine = main_env
    run.seed(TARAS)

    with pytest.raises(SystemExit) as exit_info:
        auto_triage.main(["--detail"])

    assert exit_info.value.code == 2
    assert "--detail" in capsys.readouterr().err
    assert run.store.triage == {}
    assert not engine.disposed
