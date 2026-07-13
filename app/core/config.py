from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Samostalni WMS koristi vlastiti SQLite. Za Postgres postavi DATABASE_URL u .env.
    database_url: str = "sqlite:///./wms.db"

    # Potpisivanje session cookieja. OBAVEZNO promijeniti u .env na produkciji!
    secret_key: str = "dev-wms-promijeni-me-u-env"

    # Lozinka početnog admina (čita se iz .env; koristi se samo pri praznoj bazi).
    admin_password: str = "admin"


settings = Settings()
