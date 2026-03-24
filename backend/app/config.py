import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_WEAK_JWT_SECRETS = frozenset({
    "change-me-in-production",
    "dev_jwt_secret_change_in_production_32chars",
})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://backoffice:backoffice@localhost:5432/backoffice"

    # S3 / MinIO
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "backoffice"
    S3_REGION: str = "auto"

    # JWT
    JWT_SECRET: str = "change-me-in-production"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Superadmin bootstrap (legacy, optional - system now uses onboarding flow)
    SUPERADMIN_EMAIL: str | None = None
    SUPERADMIN_PASSWORD: str | None = None

    # Environment
    ENVIRONMENT: str = "development"

    # Server
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_BASE_URL: str = "http://localhost:8000"
    CORS_ORIGINS: str = "http://localhost:3000"

    # File uploads
    FILE_MAX_SIZE_BYTES: int = 10485760  # 10 MB

    # Integration framework
    ENABLE_SYNC_SCHEDULER: bool = False
    AIRWALLEX_CLIENT_ID: str | None = None
    AIRWALLEX_API_KEY: str | None = None
    AIRWALLEX_BASE_URL: str = "https://api.airwallex.com"
    AIRWALLEX_WEBHOOK_SECRET: str | None = None
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    WISE_API_TOKEN: str | None = None
    ETHERSCAN_API_KEY: str | None = None


    @model_validator(mode="after")
    def _check_production_secrets(self):
        if self.ENVIRONMENT == "production":
            if self.JWT_SECRET in _WEAK_JWT_SECRETS or len(self.JWT_SECRET) < 32:
                raise ValueError(
                    "JWT_SECRET must be a random string of at least 32 characters in production"
                )
        elif self.JWT_SECRET in _WEAK_JWT_SECRETS:
            logging.getLogger(__name__).warning(
                "JWT_SECRET is using a default value — do not use in production"
            )
        return self


settings = Settings()
