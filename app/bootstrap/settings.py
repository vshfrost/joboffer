"""Налаштування застосунку. Читаються з оточення ЛИШЕ тут, у bootstrap.

Решта коду отримує вже готові значення через конструктори. Жодного глобального
екземпляра: кожен `create_app()` будує власні Settings.
"""

from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

STATE_SECRET_MIN = 32
ALTCHA_KEY_MIN = 32
# Шлях MCP-ендпоінта на origin вебу.
MCP_PATH = "/mcp"
GATE_CALLBACK_PATH = "/auth/google/callback"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JOBOFFER_",
        frozen=True,
        extra="forbid",
    )

    environment: Literal["dev", "test", "staging", "prod"] = "dev"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8797, ge=1, le=65535)
    # postgresql+psycopg://user:password@host:5432/db — секрет: у repr і логах прихований.
    database_url: SecretStr
    # Тека з файлами промптів (`<область>/<імʼя>.md`); у образі її задає JOBOFFER_PROMPTS_DIR.
    prompts_dir: Path = Path(__file__).resolve().parents[1] / "prompts"
    # Теки з HTML-шаблонами; у образі її задає JOBOFFER_TEMPLATES_DIR.
    templates_dir: Path = Path(__file__).resolve().parents[1] / "templates"
    # Тека з PDF версій документів (`<id документа>.pdf`); у образі й compose — volume `/data/documents`.
    documents_dir: Path = Path("/data/documents")
    # Адреса вебу, з якої користувач відкриває PDF (`<адреса>/api/documents/<номер>/pdf`).
    # Її origin — також origin агента (MCP): `agent_public_url`.
    web_public_url: str = "http://localhost:5174"
    agent_allowed_hosts: tuple[str, ...] = ("127.0.0.1:*", "localhost:*")
    # Куди дозволено віддавати код: точна адреса, «…/*» (один сегмент-ID) або «loopback».
    agent_redirect_allowlist: tuple[str, ...] = (
        "https://claude.ai/api/mcp/auth_callback",
        "loopback",
    )
    # Вхід через Google (OIDC, Authlib). Без цих значень кнопки Google нема, пароль працює.
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    # Рівно та адреса, що вписана в OAuth-клієнт Google (посимвольно): https://<хост>/api/auth/google/callback.
    google_redirect_uri: str | None = None
    # Куди Google повертає в логін-гейті MCP (агент): `<agent_public_url>/auth/google/callback`.
    google_gate_redirect_uri: str | None = None
    google_metadata_url: str = (
        "https://accounts.google.com/.well-known/openid-configuration"
    )
    # Синк пошти (процес `python -m bootstrap.sync_mail`): скринька застосунку в Gmail і її OAuth-креди.
    # У app і agent їх нема — refresh token має лише контейнер синку.
    mail_address: str = ""
    gmail_client_id: str | None = None
    gmail_client_secret: SecretStr | None = None
    gmail_refresh_token: SecretStr | None = None
    # Відправка листів (лише процес app): окремий refresh token зі scope gmail.send; client id і
    # secret ті самі. Без токена листів нема, тож реєстрація закрита. Ліміт — листів за ковзні 24 год.
    gmail_send_refresh_token: SecretStr | None = None
    mail_send_daily_limit: int = Field(default=50, ge=1)
    # Секрет підпису cookie зі станом OAuth-флоу (state, nonce, PKCE) на час входу.
    auth_state_secret: SecretStr | None = None
    # Сесії входу: простій (ковзний) і абсолютний строк; cookie лише по HTTPS, окрім dev.
    session_idle_hours: int = Field(default=12, ge=1, le=720)
    session_absolute_days: int = Field(default=30, ge=1, le=365)
    # Типово `__Host-joboffer_session` (Secure, Path=/, без Domain), а без Secure (dev по http) —
    # `joboffer_session`: браузер відкидає __Host- без Secure.
    session_cookie_name: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]+$")
    cookie_secure: bool = True
    # Скільки reverse proxy стоїть перед застосунком: з X-Forwarded-For береться запис
    # на цій глибині справа. 0 — заголовок ігнорується (його можна підробити).
    trusted_proxies: int = Field(default=0, ge=0, le=5)
    # Altcha (proof-of-work при реєстрації): секрет підпису задач; без нього реєстрація закрита.
    altcha_hmac_key: SecretStr | None = None
    altcha_maxnumber: int = Field(default=100_000, ge=1, le=10_000_000)
    # Реєстрація: closed — закрита (за замовчуванням), invite — лише за одноразовим запрошенням.
    signup_mode: Literal["closed", "invite"] = "closed"
    # Заголовок з адресою клієнта від Cloudflare (`cf-connecting-ip`); береться лише від локального
    # проксі (loopback/приватна адреса), від решти ігнорується. Не задано — як раніше.
    client_ip_header: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]+$")

    @property
    def session_cookie(self) -> str:
        if self.session_cookie_name is not None:
            return self.session_cookie_name
        return "__Host-joboffer_session" if self.cookie_secure else "joboffer_session"

    @property
    def mail_sending_enabled(self) -> bool:
        return all(
            (
                self.mail_address,
                self.gmail_client_id,
                self.gmail_client_secret,
                self.gmail_send_refresh_token,
            )
        )

    @property
    def agent_public_url(self) -> str:
        """Публічна адреса агента = resource OAuth (RFC 8707): `<origin вебу>/mcp`, шлях вебу не береться до уваги."""
        parts = urlsplit(self.web_public_url)
        return f"{parts.scheme}://{parts.netloc}{MCP_PATH}"

    @property
    def google_enabled(self) -> bool:
        return self.google_client_id is not None

    @property
    def google_gate_enabled(self) -> bool:
        return self.google_enabled and self.google_gate_redirect_uri is not None

    @field_validator(
        "google_client_id",
        "google_client_secret",
        "google_redirect_uri",
        "google_gate_redirect_uri",
        "auth_state_secret",
        "client_ip_header",
        "gmail_client_id",
        "gmail_client_secret",
        "gmail_refresh_token",
        "altcha_hmac_key",
        "gmail_send_refresh_token",
        mode="before",
    )
    @classmethod
    def _blank_means_unset(cls, value: object) -> object:
        # Compose передає порожній рядок, коли змінної в infra/.env нема.
        return None if value == "" else value

    @field_validator("client_ip_header")
    @classmethod
    def _header_names_are_lowercase(cls, value: str | None) -> str | None:
        return None if value is None else value.lower()

    @model_validator(mode="after")
    def _host_cookie_needs_secure(self) -> Self:
        name = self.session_cookie_name
        if name is not None and name.startswith("__Host-") and not self.cookie_secure:
            raise ValueError("__Host-: префікс потребує JOBOFFER_COOKIE_SECURE=true")
        return self

    @model_validator(mode="after")
    def _google_is_all_or_nothing(self) -> Self:
        parts = (
            self.google_client_id,
            self.google_client_secret,
            self.google_redirect_uri,
            self.auth_state_secret,
        )
        if all(part is None for part in parts):
            if self.google_gate_redirect_uri is not None:
                raise ValueError("google_gate_redirect_uri без налаштованого Google")
            return self
        if any(part is None for part in parts):
            raise ValueError(
                "Google: потрібні всі чотири значення (client id, client secret, redirect uri, auth state secret) або жодного"
            )
        for uri in (self.google_redirect_uri, self.google_gate_redirect_uri):
            parsed = urlsplit(uri or "")
            if uri is not None and (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.fragment
            ):
                raise ValueError(
                    "Адреса повернення Google має бути http(s)-адресою без фрагмента"
                )
        if (
            self.google_gate_redirect_uri is not None
            and self.google_gate_redirect_uri
            != f"{self.agent_public_url}{GATE_CALLBACK_PATH}"
        ):
            raise ValueError(
                f"google_gate_redirect_uri має бути {self.agent_public_url}{GATE_CALLBACK_PATH}"
            )
        if (
            self.auth_state_secret is not None
            and len(self.auth_state_secret.get_secret_value()) < STATE_SECRET_MIN
        ):
            raise ValueError(
                f"auth_state_secret — щонайменше {STATE_SECRET_MIN} символів"
            )
        return self

    @model_validator(mode="after")
    def _altcha_key_is_long_enough(self) -> Self:
        if (
            self.altcha_hmac_key is not None
            and len(self.altcha_hmac_key.get_secret_value()) < ALTCHA_KEY_MIN
        ):
            raise ValueError(f"altcha_hmac_key — щонайменше {ALTCHA_KEY_MIN} символів")
        return self

    @model_validator(mode="after")
    def _web_url_is_http(self) -> Self:
        parts = urlsplit(self.web_public_url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("web_public_url має бути http(s)-адресою")
        return self

    @model_validator(mode="after")
    def _idle_within_absolute(self) -> Self:
        if self.session_idle_hours > self.session_absolute_days * 24:
            raise ValueError(
                "session_idle_hours не може перевищувати session_absolute_days"
            )
        return self
