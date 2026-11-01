from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NagarFlow API"
    database_url: str = (
        "postgresql+psycopg://nagarflow:change-this-local-password"
        "@127.0.0.1:5433/nagarflow"
    )
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    jwt_secret_key: str = "development-only-replace-before-deploy"
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


settings = Settings()
