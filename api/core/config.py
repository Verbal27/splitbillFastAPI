import os
from pathlib import Path
from fastapi_mail import ConnectionConfig
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    db_host: str = os.getenv("DB_HOST", os.getenv("PGHOST", "localhost"))
    db_port: int = int(os.getenv("DB_PORT", os.getenv("PGPORT", 5432)))
    db_user: str = os.getenv("DB_USER", os.getenv("PGUSER", "postgres"))
    db_pass: str = os.getenv("DB_PASS", os.getenv("PGPASSWORD", "secret"))
    db_name: str = os.getenv("DB_NAME", os.getenv("PGDATABASE", "SplitBillFastApi"))

    @property
    def DATABASE_URL_asyncpg(self):
        return f"postgresql+asyncpg://{self.db_user}:{self.db_pass}@{self.db_host}:{self.db_port}/{self.db_name}"

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env")

    # Auth
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Mailing
    mail_username: str
    mail_password: SecretStr
    mail_from: str
    mail_port: int
    mail_server: str
    mail_starttls: bool = True
    mail_ssl_tls: bool = False
    mail_use_credentials: bool = True
    mail_validate_certs: bool = True

    @property
    def mail_conf(self) -> ConnectionConfig:
        """Return a ready-to-use FastAPI-Mail ConnectionConfig."""
        return ConnectionConfig(
            MAIL_USERNAME=self.mail_username,
            MAIL_PASSWORD=self.mail_password,
            MAIL_FROM=self.mail_from,
            MAIL_PORT=self.mail_port,
            MAIL_SERVER=self.mail_server,
            MAIL_STARTTLS=self.mail_starttls,
            MAIL_SSL_TLS=self.mail_ssl_tls,
            USE_CREDENTIALS=self.mail_use_credentials,
            VALIDATE_CERTS=self.mail_validate_certs,
        )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    url: str


settings = Settings()  # type: ignore
