"""Runtime settings.

Everything is read from the environment. `.env` next to the project root is
loaded for local development only; production is expected to inject real
environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path | None = None) -> None:
    target = path or ROOT / ".env"
    if not target.exists():
        return
    for raw in target.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # tenancy
    registration_codes: tuple[str, ...]
    session_cookie: str
    session_days: int
    token_encryption_key: str
    cookie_secure: bool

    # storage
    database_url: str
    upload_dir: Path

    # platform app (shared by all tenants; each shop keeps its own token)
    app_key: str
    app_secret: str
    gateway: str
    authorize_url: str
    append_operation_to_url: bool
    timeout_seconds: float
    oauth_redirect_uri: str
    oauth_success_url: str
    oauth_error_url: str
    dev_access_token: str

    # ai
    ai_enabled: bool
    cors_origin_regex: str

    @property
    def has_platform_app(self) -> bool:
        return bool(self.app_key and self.app_secret)


def _database_url() -> str:
    explicit = os.environ.get("DATABASE_URL")
    if explicit:
        return explicit
    path = Path(os.environ.get("DATABASE_PATH", "data/auto-shoper.db"))
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def _upload_dir() -> Path:
    path = Path(os.environ.get("UPLOAD_DIR", "data/uploads"))
    if not path.is_absolute():
        path = ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_settings() -> Settings:
    codes = tuple(
        code.strip() for code in os.environ.get("REGISTRATION_CODES", "").split(",") if code.strip()
    )
    return Settings(
        registration_codes=codes,
        session_cookie=os.environ.get("SESSION_COOKIE_NAME", "auto_shoper_session"),
        session_days=int(os.environ.get("SESSION_DAYS", "30")),
        token_encryption_key=os.environ.get("TOKEN_ENCRYPTION_KEY", ""),
        cookie_secure=_bool("COOKIE_SECURE", False),
        database_url=_database_url(),
        upload_dir=_upload_dir(),
        app_key=os.environ.get("ALIBABA_APP_KEY", ""),
        app_secret=os.environ.get("ALIBABA_APP_SECRET", ""),
        gateway=os.environ.get("ALIBABA_GATEWAY", "https://openapi-api.alibaba.com/rest"),
        authorize_url=os.environ.get("ALIBABA_AUTHORIZE_URL", "https://openapi-auth.alibaba.com/oauth/authorize"),
        append_operation_to_url=_bool("ALIBABA_APPEND_OPERATION_TO_URL", False),
        timeout_seconds=float(os.environ.get("ALIBABA_TIMEOUT_SECONDS", "30")),
        oauth_redirect_uri=os.environ.get(
            "ALIBABA_OAUTH_REDIRECT_URI", "http://127.0.0.1:8000/api/v1/alibaba/oauth/callback"
        ),
        oauth_success_url=os.environ.get("ALIBABA_OAUTH_SUCCESS_URL", "/#/shops?alibaba=connected"),
        oauth_error_url=os.environ.get("ALIBABA_OAUTH_ERROR_URL", "/#/shops?alibaba=error"),
        dev_access_token=os.environ.get("ALIBABA_ACCESS_TOKEN", ""),
        ai_enabled=bool(os.environ.get("OPENAI_API_KEY")),
        cors_origin_regex=os.environ.get("CORS_ALLOW_ORIGIN_REGEX", ""),
    )


settings = load_settings()
