"""Application settings, loaded from environment variables (and an optional .env)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Core -------------------------------------------------------------------
    environment: str = "development"
    debug: bool = False
    secret_key: str = "dev-secret-key-change-me-in-production"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    public_app_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"
    port: int = 8000

    # Comma separated lists kept as strings so .env stays simple.
    cors_origins: str = "http://localhost:5173"
    trusted_hosts: str = "localhost,127.0.0.1"

    # Database ---------------------------------------------------------------
    database_url: str = "postgresql+psycopg://vibespace:vibespace@localhost:5432/vibespace"
    database_pool_size: int = 5
    database_max_overflow: int = 10

    # Redis / workers --------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False

    # Object storage ---------------------------------------------------------
    s3_endpoint_url: str | None = None
    s3_region: str = "auto"
    s3_bucket: str = "vibespace-media"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_public_base_url: str | None = None
    s3_use_path_style: bool = False
    upload_max_bytes: int = 262_144_000
    upload_url_ttl_seconds: int = 900
    media_url_ttl_seconds: int = 3600

    # Cloudflare R2 (S3-compatible). When these are set they fill in the S3_*
    # settings above, so no separate storage code path is needed.
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket_name: str | None = None
    r2_public_base_url: str | None = None
    r2_endpoint_url: str | None = None

    # Video processing -------------------------------------------------------
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    video_renditions: str = "720p,480p"
    video_processing_enabled: bool = True

    # Email ------------------------------------------------------------------
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "no-reply@example.com"
    smtp_from_name: str = "VibeSpace"
    smtp_use_tls: bool = True

    # Abuse controls ---------------------------------------------------------
    rate_limit_auth_per_minute: int = 10
    rate_limit_write_per_minute: int = 120
    rate_limit_upload_per_hour: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        # Browsers always send the Origin header without a trailing slash
        # ("https://app.vercel.app"), and Starlette compares origins as exact
        # strings, so any configured value must be normalized the same way.
        return [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    def model_post_init(self, __context: object) -> None:
        """Map Cloudflare R2 settings onto the generic S3-compatible ones."""
        if self.r2_account_id and not self.r2_endpoint_url:
            self.r2_endpoint_url = f"https://{self.r2_account_id}.r2.cloudflarestorage.com"
        if self.r2_endpoint_url:
            self.s3_endpoint_url = self.r2_endpoint_url
            self.s3_region = "auto"
        if self.r2_bucket_name:
            self.s3_bucket = self.r2_bucket_name
        if self.r2_access_key_id:
            self.s3_access_key_id = self.r2_access_key_id
        if self.r2_secret_access_key:
            self.s3_secret_access_key = self.r2_secret_access_key
        if self.r2_public_base_url:
            self.s3_public_base_url = self.r2_public_base_url.rstrip("/")

    @property
    def storage_backend(self) -> str | None:
        if not self.storage_configured:
            return None
        return "cloudflare_r2" if self.r2_account_id else "s3_compatible"

    @property
    def rendition_list(self) -> list[str]:
        return [item.strip() for item in self.video_renditions.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def email_delivery_configured(self) -> bool:
        return bool(self.smtp_host)

    @property
    def storage_configured(self) -> bool:
        return bool(self.s3_bucket and self.s3_access_key_id and self.s3_secret_access_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()