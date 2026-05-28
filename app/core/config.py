from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    database_url: str
    jwt_secret: str
    jwt_access_token_expires_minutes: int = 30
    jwt_refresh_token_expires_days: int = 30

    # Admin configuration (comma-separated user UUIDs in .env)
    admin_user_ids: str = ""
    online_timeout_minutes: int = 15


settings = Settings()
