"""Кроки для features/signup.feature: use cases реєстрації + in-memory адаптери через портал."""

import hashlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import datetime, timedelta
from string import Template
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given, parsers, scenarios, then, when

from application.contracts.sessions import SessionIssued
from application.contracts.signup import Signup, SignupAccepted, VerifySignup
from application.identity.altcha import AltchaUseCases
from application.identity.invites import SignupInviteUseCases
from application.identity.sessions import SessionServices, SessionUseCases
from application.identity.signup import SignupServices, SignupUseCases
from application.identity.use_cases import IdentityUseCases
from application.mail.outgoing import OutgoingMailServices, OutgoingMailUseCases
from domain.identity.altcha import AltchaPolicy
from domain.identity.email import Email
from domain.identity.errors import CodeIncorrect, TooManyAttempts
from domain.identity.ids import SessionId, UserId
from domain.identity.password import PasswordHash
from domain.identity.session import Session, SessionPolicy
from domain.identity.signup import SignupMode
from domain.identity.user import DisplayName, User
from domain.mail.outgoing import MailUnavailable, OutgoingMail
from domain.shared.errors import DomainError
from tests.support.altcha import (
    TEST_KEY,
    CountingAltchaRandom,
    InMemoryAltchaUnitOfWork,
    solve_challenge,
)
from tests.support.clock import FakeClock
from tests.support.identity import FakePasswordHasher
from tests.support.ids import SequentialIds
from tests.support.invites import InMemoryInviteUnitOfWork
from tests.support.outgoing import (
    BODY,
    EXISTS_BODY,
    EXISTS_SUBJECT,
    SUBJECT,
    FakeAudit,
    FakeSender,
    FakeTemplates,
    InMemorySendUnitOfWork,
    SendStore,
)
from tests.support.sessions import InMemoryAuthUnitOfWork, SequentialTokens
from tests.support.signup import (
    FakeLegalDocuments,
    InMemorySignupUnitOfWork,
    SequentialCodes,
    SignupStores,
)

scenarios("features/signup.feature")

POLICY = SessionPolicy(idle=timedelta(hours=12), absolute=timedelta(hours=48))
CODE = re.compile(r"\b\d{6}\b")
PASSWORD = "Correct-Horse-9"
UNKNOWN_ID = "00000000-0000-0000-0000-0000000000ff"


class Settings:
    mode = SignupMode.INVITE


class World:
    """Усе, що живе протягом одного сценарію: сховища, фейки, use cases і результати кроків."""

    def __init__(
        self,
        portal: BlockingPortal,
        clock: FakeClock,
        ids: SequentialIds,
        settings: Settings,
    ) -> None:
        self.portal, self.clock, self.ids, self.settings = portal, clock, ids, settings
        self.stores = SignupStores()
        self.sessions: dict[SessionId, Session] = {}
        self.used_altchas: dict[str, datetime] = {}
        self.send_store = SendStore()
        self.sender = FakeSender()
        self.legal = FakeLegalDocuments()
        self.hasher = FakePasswordHasher()
        self.tokens = SequentialTokens()
        self.altcha = AltchaUseCases(
            lambda: InMemoryAltchaUnitOfWork(self.used_altchas),
            clock,
            CountingAltchaRandom(),
            AltchaPolicy(key=TEST_KEY, max_number=200),
        )
        self.mail = OutgoingMailUseCases(
            lambda: InMemorySendUnitOfWork(self.send_store),
            clock,
            OutgoingMailServices(
                sender=self.sender,
                templates=FakeTemplates(),
                audit=FakeAudit(),
                daily_limit=50,
            ),
        )
        identity = IdentityUseCases(self._auth_uow, clock, ids, self.hasher)
        self.session_uc = SessionUseCases(
            self._auth_uow,
            identity,
            SessionServices(clock=clock, ids=ids, tokens=self.tokens, policy=POLICY),
        )
        self.codes = SequentialCodes()
        self.invite_token = ""
        self.accepted: list[SignupAccepted] = []
        self.signed_up_at: list[datetime] = []
        self.last_altcha = ""
        self.issued: SessionIssued | None = None
        self.errors: list[DomainError] = []

    def _auth_uow(self) -> InMemoryAuthUnitOfWork:
        return InMemoryAuthUnitOfWork(
            self.stores.users, self.sessions, self.stores.failures
        )

    @property
    def invites(self) -> SignupInviteUseCases:
        return SignupInviteUseCases(
            lambda: InMemoryInviteUnitOfWork(self.stores.invites, self.stores.failures),
            self.clock,
            self.ids,
            self.tokens,
            self.settings.mode,
        )

    @property
    def signup(self) -> SignupUseCases:
        return SignupUseCases(
            lambda: InMemorySignupUnitOfWork(self.stores),
            SignupServices(
                clock=self.clock,
                ids=self.ids,
                hasher=self.hasher,
                codes=self.codes,
                altcha=self.altcha,
                invites=self.invites,
                legal=self.legal,
                sessions=self.session_uc,
                mail=self.mail,
                mode=self.settings.mode,
            ),
        )

    def run[T](self, action: Callable[[], Awaitable[T]]) -> T | None:
        try:
            return self.portal.call(action)
        except DomainError as error:
            self.errors.append(error)
            return None

    def solve(self) -> str:
        challenge = self.portal.call(self.altcha.issue)
        return solve_challenge(**asdict(challenge))

    def register(self, **overrides: str) -> None:
        fields = {
            "email": "taras@example.com",
            "password": PASSWORD,
            "display_name": "",
            "invite": self.invite_token,
            "terms_version": self.legal.version,
            "altcha": "",
            "website": "",
            "client": "10.0.0.1",
        }
        fields.update(overrides)
        if not fields["altcha"]:
            fields["altcha"] = self.solve()
        self.last_altcha = fields["altcha"]
        self.signed_up_at.append(self.clock.now())
        accepted = self.run(lambda: self.signup.signup(Signup(**fields)))
        if accepted is not None:
            self.accepted.append(accepted)

    def verify(self, signup_id: str, code: str) -> None:
        command = VerifySignup(signup_id=signup_id, code=code)
        issued = self.run(lambda: self.signup.verify(command))
        if issued is not None:
            self.issued = issued

    def code_mails(self) -> list[OutgoingMail]:
        return [mail for mail in self.sender.sent if CODE.search(mail.body)]

    def code_of(self, mail: OutgoingMail) -> str:
        found = CODE.search(mail.body)
        assert found is not None
        return found.group()

    def last_code(self) -> str:
        mails = self.code_mails()
        assert mails, "лист із кодом не надсилали"
        return self.code_of(mails[-1])

    def first_code(self) -> str:
        mails = self.code_mails()
        assert mails, "лист із кодом не надсилали"
        return self.code_of(mails[0])

    def user(self, email: str) -> User | None:
        return next(
            (u for u in self.stores.users.values() if u.email.value == email), None
        )


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def world(
    portal: BlockingPortal, clock: FakeClock, ids: SequentialIds, settings: Settings
) -> World:
    return World(portal, clock, ids, settings)


@given("реєстрація працює за запрошенням")
def signup_by_invite(settings: Settings) -> None:
    settings.mode = SignupMode.INVITE


@given("реєстрація закрита")
def signup_closed(settings: Settings) -> None:
    settings.mode = SignupMode.CLOSED


@given("є дійсне запрошення")
def valid_invite(world: World) -> None:
    issued = world.portal.call(world.invites.create)
    world.invite_token = issued.token


@given(parsers.parse('у системі вже є користувач "{email}"'))
def existing_user(world: World, email: str) -> None:
    user = User.register(
        id=UserId(world.ids.new()),
        email=Email(email),
        display_name=DisplayName("Наталя"),
        password_hash=PasswordHash("fake$0001$existing"),
        now=world.clock.now(),
    )
    world.stores.users[user.id] = user


@given("пошта недоступна")
@when("пошта недоступна")
def mail_down(world: World) -> None:
    world.sender.error = MailUnavailable("Gmail недоступний")


@given("добовий ліміт листів вичерпано")
def mail_quota_used(world: World) -> None:
    world.send_store.moments[:] = [world.clock.now()] * 50


@when(parsers.parse('я реєструюсь як "{email}" з паролем "{password}"'))
def register(world: World, email: str, password: str) -> None:
    world.register(email=email, password=password)


@when(parsers.parse('я реєструюсь як "{email}" з паролем довжиною {size:d} символів'))
def register_long_password(world: World, email: str, size: int) -> None:
    world.register(email=email, password="x" * size)


@when(parsers.parse('я реєструюсь як "{email}" з клієнта "{client}"'))
def register_from(world: World, email: str, client: str) -> None:
    world.register(email=email, client=client)


@when(parsers.parse('я реєструюсь {count:d} разів з клієнта "{client}"'))
def register_many(world: World, count: int, client: str) -> None:
    for number in range(count):
        world.register(email=f"user{number}@example.com", client=client)
    assert world.errors == []


@when(parsers.parse('я реєструюсь як "{email}" з тим самим розв\'язком ALTCHA'))
def register_same_altcha(world: World, email: str) -> None:
    world.register(email=email, altcha=world.last_altcha)


@when(parsers.parse('я реєструюсь з імʼям "{name}"'))
def register_named(world: World, name: str) -> None:
    world.register(display_name=name)


@when("я реєструюсь без згоди з умовами")
def register_without_terms(world: World) -> None:
    world.register(terms_version="")


@when(parsers.parse('я реєструюсь з версією умов "{version}"'))
def register_old_terms(world: World, version: str) -> None:
    world.register(terms_version=version)


@when("я реєструюсь із недійсним розв'язком ALTCHA")
def register_bad_altcha(world: World) -> None:
    world.register(altcha="not-a-solution")


@when(parsers.parse('я реєструюсь із запрошенням "{token}"'))
def register_with_invite(world: World, token: str) -> None:
    world.register(invite=token)


@when("я реєструюсь із заповненим полем приманки")
def register_honeypot(world: World) -> None:
    world.register(website="https://spam.example.com")


@when("я підтверджую реєстрацію правильним кодом")
def verify_right(world: World) -> None:
    world.verify(world.accepted[-1].signup_id, world.last_code())


@when("я підтверджую реєстрацію першим кодом")
def verify_first_code(world: World) -> None:
    world.verify(world.accepted[-1].signup_id, world.first_code())


@when("я підтверджую реєстрацію першим запитом і першим кодом")
def verify_first_request(world: World) -> None:
    world.verify(world.accepted[0].signup_id, world.first_code())


@when(parsers.parse('я підтверджую реєстрацію кодом "{code}"'))
def verify_with(world: World, code: str) -> None:
    world.verify(world.accepted[-1].signup_id, code)


@when(parsers.parse("я підтверджую реєстрацію {count:d} невірними кодами"))
def verify_wrong_many(world: World, count: int) -> None:
    for _ in range(count):
        world.verify(world.accepted[-1].signup_id, "000000")


@when(parsers.parse('я підтверджую реєстрацію невідомого запиту кодом "{code}"'))
def verify_unknown(world: World, code: str) -> None:
    world.verify(UNKNOWN_ID, code)


@when("я прошу надіслати код ще раз")
def resend(world: World) -> None:
    signup_id = world.accepted[-1].signup_id
    world.run(lambda: world.signup.resend(signup_id))


@when(
    parsers.parse("я прошу надіслати код ще раз {count:d} рази, щоразу через 60 секунд")
)
def resend_many(world: World, count: int) -> None:
    for _ in range(count):
        world.clock.advance(timedelta(seconds=60))
        resend(world)
    assert world.errors == []


@when("я прошу надіслати код для невідомого запиту")
def resend_unknown(world: World) -> None:
    world.run(lambda: world.signup.resend(UNKNOWN_ID))


@when("хтось погашає запрошення")
def redeem_elsewhere(world: World) -> None:
    world.portal.call(world.invites.redeem, world.invite_token)


@when(parsers.re(r"минає (?P<seconds>\d+) секунд\w*"))
def pass_seconds(world: World, seconds: str) -> None:
    world.clock.advance(timedelta(seconds=int(seconds)))


@when(parsers.re(r"минає (?P<minutes>\d+) хвилин\w*"))
def pass_minutes(world: World, minutes: str) -> None:
    world.clock.advance(timedelta(minutes=int(minutes)))


@then("реєстрація прийнята")
def accepted(world: World) -> None:
    assert world.errors == []
    assert len(world.accepted) >= 1
    UUID(world.accepted[-1].signup_id)


@then(parsers.parse('лист із шестицифровим кодом надіслано на "{email}"'))
def code_mail_sent(world: World, email: str) -> None:
    assert len(world.sender.sent) == 1
    mail = world.sender.sent[0]
    code = world.code_of(mail)
    assert (mail.to, mail.subject) == (email, SUBJECT)
    assert mail.body == Template(BODY).substitute(code=code)


@then(parsers.parse('лист «акаунт уже є» без коду надіслано на "{email}"'))
def exists_mail_sent(world: World, email: str) -> None:
    assert world.sender.sent == [
        OutgoingMail(to=email, subject=EXISTS_SUBJECT, body=EXISTS_BODY)
    ]
    assert CODE.search(world.sender.sent[0].body) is None


@then("жодного листа не надіслано")
def no_mail(world: World) -> None:
    assert world.sender.sent == []


@then(parsers.re(r"надіслано (?P<count>\d+) лист\w*"))
def mails_sent(world: World, count: str) -> None:
    assert len(world.sender.sent) == int(count)


@then("новий код відрізняється від попереднього")
def code_changed(world: World) -> None:
    first, second = (world.code_of(mail) for mail in world.code_mails()[-2:])
    assert first != second


@then(parsers.parse('користувача "{email}" у системі нема'))
def no_user(world: World, email: str) -> None:
    assert world.user(email) is None


@then("у сховищі запитів лише хеш пароля й digest коду")
def only_hashes(world: World) -> None:
    assert len(world.stores.requests) == 1
    request = next(iter(world.stores.requests.values()))
    code = world.last_code()
    expected = hashlib.sha256(f"{request.id.value}{code}".encode()).hexdigest()
    assert str(request.id.value) == world.accepted[-1].signup_id
    assert request.code_digest == expected
    assert request.password_hash.value != PASSWORD
    assert PASSWORD not in request.password_hash.value
    assert code not in repr(request)
    assert PASSWORD not in repr(request)


@then(parsers.parse('я отримую сесію користувача "{email}"'))
def got_session(world: World, email: str) -> None:
    assert world.issued is not None
    assert world.issued.user.email == email
    user = world.user(email)
    assert user is not None
    assert [session.user_id for session in world.sessions.values()] == [user.id]


@then(
    parsers.parse(
        'користувач "{email}" має версію умов "{version}", прийняту під час реєстрації'
    )
)
def has_terms(world: World, email: str, version: str) -> None:
    user = world.user(email)
    assert user is not None
    assert (user.terms_version, user.terms_accepted_at) == (
        version,
        world.signed_up_at[0],
    )


@then(parsers.parse('користувач "{email}" входить з паролем "{password}"'))
def can_log_in(world: World, email: str, password: str) -> None:
    user = world.user(email)
    assert user is not None
    assert world.portal.call(world.hasher.verify, password, user.password_hash)


@then(parsers.parse('імʼя користувача "{email}" — "{name}"'))
def display_name(world: World, email: str, name: str) -> None:
    user = world.user(email)
    assert user is not None
    assert user.display_name.value == name


@then("запрошення погашене")
def invite_redeemed(world: World) -> None:
    assert [i.used_at is not None for i in world.stores.invites.values()] == [True]


@then("запрошення ціле")
def invite_intact(world: World) -> None:
    assert [i.used_at is None for i in world.stores.invites.values()] == [True]


@then("у сховищі нема запитів на реєстрацію")
def no_requests(world: World) -> None:
    assert world.stores.requests == {}


@then(parsers.re(r"у сховищі (?P<count>\d+) запит\w* на реєстрацію"))
def requests_count(world: World, count: str) -> None:
    assert len(world.stores.requests) == int(count)


@then("розв'язок ALTCHA не використано")
def altcha_untouched(world: World) -> None:
    assert world.used_altchas == {}


@then("жодної помилки")
def no_errors(world: World) -> None:
    assert world.errors == []


@then(parsers.parse('отримую помилку "{code}"'))
def got_error(world: World, code: str) -> None:
    assert [error.code for error in world.errors] == [code]


@then(parsers.parse('отримую помилки "{codes}"'))
def got_errors(world: World, codes: str) -> None:
    assert [error.code for error in world.errors] == codes.split(", ")


@then(parsers.parse('остання помилка — "{code}"'))
def last_error(world: World, code: str) -> None:
    assert world.errors
    assert world.errors[-1].code == code


@then(
    parsers.re(
        r'(?:отримую помилку|остання помилка —) "(?P<code>\w+)" і залишилось (?P<left>\d+) спроб\w*'
    )
)
def attempts_left(world: World, code: str, left: str) -> None:
    assert world.errors
    error = world.errors[-1]
    assert error.code == code
    assert isinstance(error, CodeIncorrect)
    assert error.attempts_left == int(left)


@then(parsers.parse('отримую помилку "{code}" з очікуванням {seconds:d} секунд'))
def got_throttled(world: World, code: str, seconds: int) -> None:
    assert [error.code for error in world.errors] == [code]
    error = world.errors[0]
    assert isinstance(error, TooManyAttempts)
    assert error.retry_after == seconds
