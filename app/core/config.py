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
    wechat_app_id: str | None = None
    wechat_app_secret: str | None = None
    wechat_api_base: str = "https://api.weixin.qq.com"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False

    # CORS allowed origins (comma-separated). Empty means same-origin only,
    # which is the default for the Nginx-proxied deployment where the web UI
    # and the API share one origin.
    cors_origins: str = ""

    # Trusted proxy hops for X-Forwarded-For. 0 means do not trust the header
    # at all (direct access only); 1 is the typical setup behind one Nginx.
    trusted_proxy_hops: int = 0


settings = Settings()
