from pydantic_settings import BaseSettings

# Local-only escape hatch: set USE_SQLITE=true to run against a throwaway
# sqlite file instead of Postgres/Neon. Prod must never set this.
_SQLITE_FALLBACK_URL = "sqlite:///./coopera.db"


class Settings(BaseSettings):
    # No default on purpose: both local dev and prod are expected to point
    # at a real Postgres/Neon database via DATABASE_URL. Set USE_SQLITE=true
    # locally if you want zero-setup sqlite instead.
    database_url: str = ""
    use_sqlite: bool = False
    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 480

    # Gestor (mobile meter-reader) tokens use their own, shorter-lived access
    # token backed by a long-lived refresh token, so a field worker whose
    # token expires mid-route gets silently refreshed instead of logged out
    # (see mobile/src/lib/api.ts). Admin/platform logins still use the plain
    # jwt_expire_minutes above.
    jwt_gestor_access_expire_minutes: int = 60
    jwt_gestor_refresh_expire_days: int = 30

    cors_origins: str = "http://localhost:5173"

    # Public URL this API is reachable at. Used to build absolute URLs for
    # files saved to local disk (the fallback used when R2 isn't configured)
    # and as the base for the Mercado Pago OAuth redirect/webhook URLs.
    public_base_url: str = "http://localhost:8000"

    # Public URL of the frontend. Used to send the admin back to the right
    # page after the Mercado Pago OAuth "Connect" flow.
    frontend_base_url: str = "http://localhost:5173"

    # Mercado Pago OAuth "Connect" app credentials (one per Coopera
    # deployment, shared by all tenants). Created in the Mercado Pago
    # developers panel: https://www.mercadopago.com.ar/developers/panel/app
    # Each cooperativa then connects *their own* MP account to this app, so
    # payments settle directly to them, not to Coopera.
    mp_client_id: str | None = None
    mp_client_secret: str | None = None

    # Cloudflare R2 (S3-compatible). Optional: when any of these is missing,
    # uploaded logos are stored on local disk under `upload_dir` instead.
    r2_endpoint_url: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket_name: str | None = None
    r2_public_base_url: str | None = None

    upload_dir: str = "uploads"

    # Hard cap on reading-photo uploads from the gestor mobile app, enforced
    # while streaming the body in (see routers/gestor.py) so an oversized or
    # unbounded upload can't be buffered fully into memory first.
    max_reading_photo_bytes: int = 8 * 1024 * 1024

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

    @property
    def mp_configured(self) -> bool:
        return bool(self.mp_client_id and self.mp_client_secret)

    @property
    def mp_redirect_uri(self) -> str:
        """Single, fixed callback URL registered in the Mercado Pago app.
        Which tenant is connecting travels in the signed `state` param
        instead, so this doesn't need to vary per tenant."""
        return f"{self.public_base_url.rstrip('/')}/api/mp/oauth/callback"


def _resolve_database_url(raw: "Settings") -> str:
    if raw.use_sqlite:
        return _SQLITE_FALLBACK_URL
    if not raw.database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Point it at your Neon/Postgres "
            "database, or set USE_SQLITE=true for local-only sqlite."
        )
    return raw.database_url


settings = Settings()
settings.database_url = _resolve_database_url(settings)
