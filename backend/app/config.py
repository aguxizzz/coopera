from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./coopera.db"
    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 480
    cors_origins: str = "http://localhost:5173"

    # Public URL this API is reachable at. Used to build absolute URLs for
    # files saved to local disk (the fallback used when R2 isn't configured).
    public_base_url: str = "http://localhost:8000"

    # Cloudflare R2 (S3-compatible). Optional: when any of these is missing,
    # uploaded logos are stored on local disk under `upload_dir` instead.
    r2_endpoint_url: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket_name: str | None = None
    r2_public_base_url: str | None = None

    upload_dir: str = "uploads"

    class Config:
        env_file = ".env"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def r2_configured(self) -> bool:
        return bool(
            self.r2_endpoint_url
            and self.r2_access_key_id
            and self.r2_secret_access_key
            and self.r2_bucket_name
        )


settings = Settings()
