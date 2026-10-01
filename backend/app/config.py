from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./coopera.db"
    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 480
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


settings = Settings()
