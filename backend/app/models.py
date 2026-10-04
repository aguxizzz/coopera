import datetime as dt

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Tenant(Base):
    """A cooperativa. `slug` drives routing today (path-based, e.g. /t/{slug});
    `custom_domain` is reserved for when each tenant gets its own domain."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    custom_domain: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    mp_alias: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mp_cbu: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mp_titular: Mapped[str | None] = mapped_column(String(255), nullable=True)
    primary_color: Mapped[str] = mapped_column(String(16), default="#2563eb")
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_whatsapp: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_primary_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_secondary_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Shared "household" password for the gestor mobile app: one password per
    # cooperativa (set by an admin), not one per gestor. Null until an admin
    # sets it, which blocks gestor device-login until then. See
    # app/routers/gestor.py's /device-login and /select-profile.
    gestor_shared_password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Mercado Pago OAuth "Connect": set once the tenant's admin authorizes
    # Coopera's MP app against their own MP account. Tokens are stored
    # Fernet-encrypted (see app/services/mercadopago.py) and refreshed
    # automatically before they expire.
    mp_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mp_access_token: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    mp_refresh_token: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    mp_public_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mp_token_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    # Helipagos: token por comercio (no OAuth, a diferencia de Mercado Pago).
    # Guardado cifrado igual que los tokens de MP (ver app/services/helipagos.py).
    helipagos_token: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Valor del header "apikey" que Helipagos manda en cada webhook; se compara
    # contra esto para validar que la notificación es legítima (Helipagos no
    # firma el payload, solo manda este secreto compartido en un header).
    helipagos_webhook_apikey: Mapped[str | None] = mapped_column(String(500), nullable=True)
    helipagos_environment: Mapped[str] = mapped_column(String(16), default="sandbox", server_default="sandbox")

    # Macro Click de Pago (Banco Macro): credenciales por comercio, sin OAuth,
    # mismo esquema que Helipagos. NO OFICIAL: implementado reconstruyendo el
    # protocolo a partir de un plugin de WooCommerce de terceros (ver
    # app/services/macroclick.py), no de documentación provista por el banco.
    macroclick_comercio_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    macroclick_sucursal: Mapped[str | None] = mapped_column(String(32), nullable=True)
    macroclick_secret_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    macroclick_environment: Mapped[str] = mapped_column(String(16), default="sandbox", server_default="sandbox")

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    admins: Mapped[list["AdminUser"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    members: Mapped[list["Member"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")


class AdminUser(Base):
    __tablename__ = "admin_users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_admin_tenant_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    email: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    # "owner": full access, including managing other admins and connecting/
    # disconnecting Mercado Pago. "staff": everyday admin tasks (socios,
    # facturas, import) but not those two. Every tenant must keep at least
    # one owner (enforced in the admin-management endpoints).
    role: Mapped[str] = mapped_column(String(16), default="owner", server_default="owner")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    tenant: Mapped[Tenant] = relationship(back_populates="admins")


class PlatformUser(Base):
    """A Coopera developer/operator. Not tied to any tenant: platform users
    create cooperativas and can access any tenant's data to troubleshoot."""

    __tablename__ = "platform_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class Member(Base):
    """A socio de la cooperativa."""

    __tablename__ = "members"
    __table_args__ = (UniqueConstraint("tenant_id", "numero_socio", name="uq_member_tenant_numero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    numero_socio: Mapped[str] = mapped_column(String(64), index=True)
    nombre: Mapped[str] = mapped_column(String(255))
    identificador: Mapped[str] = mapped_column(String(64))  # DNI o nro. de medidor, usado como 2do factor
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    tenant: Mapped[Tenant] = relationship(back_populates="members")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="member", cascade="all, delete-orphan")
    meters: Mapped[list["Meter"]] = relationship(back_populates="member", cascade="all, delete-orphan")


class ImportBatch(Base):
    """One spreadsheet upload = one period's worth of charges for a tenant."""

    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    period_year: Mapped[int]
    period_month: Mapped[int]
    filename: Mapped[str] = mapped_column(String(255))
    row_count: Mapped[int] = mapped_column(default=0)
    imported_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class Invoice(Base):
    """A charge for one member for one period, derived from an import."""

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("member_id", "period_year", "period_month", name="uq_invoice_member_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"))
    period_year: Mapped[int]
    period_month: Mapped[int]
    consumo: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    monto: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    vencimiento: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    pagado: Mapped[bool] = mapped_column(Boolean, default=False)

    # Set when a Mercado Pago payment preference/payment is created for this
    # invoice (app/services/mercadopago.py). `mp_preference_id` identifies the
    # checkout; `mp_payment_id` is filled once a payment notification for it
    # arrives via the tenant's webhook.
    mp_preference_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mp_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # ID de la "solicitud de pago" en Helipagos (id_sp). Permite consultar estado
    # y evitar crear una solicitud duplicada si el socio reintenta pagar.
    helipagos_id_sp: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    member: Mapped[Member] = relationship(back_populates="invoices")


class PdfImportProfile(Base):
    """Per-tenant recipe for parsing socios out of PDF boletas: a regex (one
    capture group) per field, e.g. {"numero_socio": "N° Socio:\\s*(\\d+)"}.
    Every cooperativa's PDF layout is different, so this is authored by a
    platform dev via /api/dev after testing it against a sample PDF — tenant
    admins only ever consume it (import-pdf), never edit it. One profile per
    tenant."""

    __tablename__ = "pdf_import_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), unique=True)
    field_patterns: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    tenant: Mapped[Tenant] = relationship()


class PdfImportJob(Base):
    """Progress tracker for a PDF import running in the background (a
    cooperativa's boletas can run thousands of pages across several sector
    PDFs, so the admin panel polls this instead of blocking the upload
    request)."""

    __tablename__ = "pdf_import_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    period_year: Mapped[int]
    period_month: Mapped[int]
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|processing|done|error
    total_pages: Mapped[int] = mapped_column(default=0)
    processed_pages: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    tenant: Mapped[Tenant] = relationship()


class AuditLog(Base):
    """Who did what, for sensitive tenant actions (Mercado Pago connect/
    disconnect, admin management, settings/logo changes, etc). `actor_email`
    is denormalized so the trail survives the actor being deleted later."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    actor_type: Mapped[str] = mapped_column(String(16))  # "admin" | "platform"
    actor_id: Mapped[int]
    actor_email: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)


class Gestor(Base):
    """A meter reader (empleado de la cooperativa que recorre el pueblo con la
    app). Separate from AdminUser on purpose: a gestor only ever needs the
    reading-capture endpoints, never the admin panel, so keeping it a
    distinct principal means we never have to remember to gate every admin
    route against this role.

    Gestores have no credentials of their own: the device logs in with the
    tenant's shared password (Tenant.gestor_shared_password_hash) and then
    picks which gestor is reading today, Netflix-profile style. `email` is
    kept only as a contact/display field. Every reading still records which
    gestor captured it (Reading.gestor_id), so the audit trail survives the
    shared login."""

    __tablename__ = "gestores"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_gestor_tenant_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    nombre: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    # Backs the mobile app's silent token refresh (see app/auth.py and
    # routers/gestor.py): only the SHA-256 hash of the current refresh token
    # is stored, rotated on every use, so a leaked DB row can't be replayed
    # as a session. Null means the gestor has no active refresh token (never
    # logged in from the app, or it was revoked/expired).
    refresh_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    refresh_token_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    tenant: Mapped[Tenant] = relationship()


class Meter(Base):
    """A medidor (luz, agua o gas) asociado a un socio. Un socio puede tener
    más de uno (ej: varias propiedades)."""

    __tablename__ = "meters"
    __table_args__ = (UniqueConstraint("tenant_id", "codigo", name="uq_meter_tenant_codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    codigo: Mapped[str] = mapped_column(String(64))  # número de medidor
    tipo: Mapped[str] = mapped_column(String(16), default="luz")  # luz | agua | gas
    direccion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unidad: Mapped[str] = mapped_column(String(16), default="kWh")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    member: Mapped[Member] = relationship(back_populates="meters")
    readings: Mapped[list["Reading"]] = relationship(back_populates="meter", cascade="all, delete-orphan")


class Reading(Base):
    """One lectura capturada por un gestor (o cargada manualmente por un
    admin). `valor_anterior`/`consumo` quedan desnormalizados en el momento
    de la carga para no tener que recalcular el historial cada vez que se
    muestra una lectura, y porque son el valor que de verdad importa
    auditar si un socio reclama una factura."""

    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id"), index=True)
    gestor_id: Mapped[int | None] = mapped_column(ForeignKey("gestores.id"), nullable=True)

    valor: Mapped[float] = mapped_column(Float)
    valor_anterior: Mapped[float | None] = mapped_column(Float, nullable=True)
    consumo: Mapped[float | None] = mapped_column(Float, nullable=True)

    foto_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ocr_valor: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ocr_confianza: Mapped[float | None] = mapped_column(Float, nullable=True)

    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Marcada automáticamente cuando el consumo se sale de rango (negativo o
    # salto anormal respecto del historial). El gestor puede seguir
    # guardando la lectura igual; esto sólo la deja señalada para que un
    # admin la revise antes de facturar.
    anomala: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)

    meter: Mapped[Meter] = relationship(back_populates="readings")
    gestor: Mapped[Gestor | None] = relationship()
