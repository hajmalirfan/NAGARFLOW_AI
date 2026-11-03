from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_JWT_SECRET = "development-only-replace-before-deploy"
# The placeholder in .env.example, long enough to pass a length check alone.
EXAMPLE_JWT_SECRET = "replace-this-with-a-long-random-secret-before-deploy"
MIN_JWT_SECRET_LENGTH = 32
DEVELOPMENT = "development"


class Settings(BaseSettings):
    app_name: str = "NagarFlow API"
    # Anything but "development" gets the production safeguards.
    environment: str = DEVELOPMENT
    database_url: str = (
        "postgresql+psycopg://nagarflow:change-this-local-password"
        "@127.0.0.1:5433/nagarflow"
    )
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    jwt_secret_key: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Scenario validation. A scenario is only marked valid when road
    # connectivity has actually been checked. Setting this to false is an
    # explicit development override for use when no road network is
    # available; every validation that relies on it is logged.
    require_road_connectivity: bool = True
    # How far a location may sit from a usable road. An assumption, not a
    # measured figure.
    road_snap_max_m: float = Field(default=200, gt=0)
    # The OpenStreetMap GeoPackage. A relative path starts at the repository
    # root. Empty means no road network, so scenarios stay incomplete.
    road_network_path: str = ""
    # How long OR-Tools may search. It uses the whole limit, because guided
    # local search keeps improving until time runs out.
    optimizer_time_limit_s: int = Field(default=10, gt=0)
    # How many runs may search at once. Another gets 503, with no queue.
    optimizer_max_concurrent: int = Field(default=2, gt=0)
    # How many proxies in front of the backend append to X-Forwarded-For. With
    # 0 the header is ignored, so a client cannot choose its own address.
    trusted_proxy_hops: int = Field(default=0, ge=0)

    # Password reset
    reset_token_expire_minutes: int = 15
    # Where the reset link should point. Must be the address the user's
    # browser can open, which in production is the deployed frontend.
    frontend_base_url: str = "http://localhost:5173"

    # Outgoing email. When smtp_host is empty the application does not
    # send real email: it writes each message to backend/dev_emails/ and
    # logs the reset link so local development works without a mail
    # server. Set these in .env to send real email.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    email_from: str = "NagarFlow <no-reply@nagarflow.local>"

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


EXAMPLE_DATABASE_PASSWORD = "change-this-local-password"
# Every placeholder in .env.production.example starts with this.
PLACEHOLDER_PREFIX = "replace-with-"
LOCAL_HOSTS = ("localhost", "127.0.0.1")
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _production_problems(values: Settings) -> list[str]:
    problems = []
    secret = values.jwt_secret_key
    if (
        secret in (DEFAULT_JWT_SECRET, EXAMPLE_JWT_SECRET)
        or secret.startswith(PLACEHOLDER_PREFIX)
        or len(secret) < MIN_JWT_SECRET_LENGTH
    ):
        problems.append(
            f"JWT_SECRET_KEY must be a private value of at least {MIN_JWT_SECRET_LENGTH} characters."
        )
    if any(host in origin for origin in values.cors_origins for host in LOCAL_HOSTS):
        problems.append("CORS_ORIGINS must list the deployed frontend, not localhost.")
    if any(host in values.frontend_base_url for host in LOCAL_HOSTS):
        problems.append("FRONTEND_BASE_URL must be the deployed frontend, not localhost.")
    if not values.smtp_host:
        problems.append("SMTP_HOST must be set, or reset links are written to disk and logged.")
    if EXAMPLE_DATABASE_PASSWORD in values.database_url or PLACEHOLDER_PREFIX in values.database_url:
        problems.append("DATABASE_URL still uses the example password.")
    if not values.road_network_path:
        problems.append("ROAD_NETWORK_PATH must point at the roads file, or no route can run.")
    return problems


def check_production_settings(values: Settings) -> None:
    """Stop the server rather than run with settings meant for one laptop."""
    if values.environment == DEVELOPMENT:
        return
    problems = _production_problems(values)
    if problems:
        raise RuntimeError(
            f"Refusing to start in the {values.environment} environment. " + " ".join(problems)
        )


def production_warnings(values: Settings) -> list[str]:
    """Problems worth logging that should not stop a start, such as a late mount."""
    if values.environment == DEVELOPMENT or not values.road_network_path:
        return []
    path = Path(values.road_network_path)
    if not path.is_absolute():
        path = REPOSITORY_ROOT / path
    if not path.is_file():
        return [f"ROAD_NETWORK_PATH points at {path}, which is not a file yet."]
    return []


def api_doc_urls(environment: str) -> dict[str, str | None]:
    """FastAPI's documentation addresses, which only development serves."""
    if environment == DEVELOPMENT:
        return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}
    return {"docs_url": None, "redoc_url": None, "openapi_url": None}


settings = Settings()
