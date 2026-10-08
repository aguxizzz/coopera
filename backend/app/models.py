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
    cuts: Mapped[list["ServiceCut"]] = relationship(back_populates="member", cascade="all, delete-orphan")


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


class GestorQrSession(Base):
    """One scan-to-login attempt for the shared gestor login — the QR
    alternative to typing the cooperativa's shared password (see
    app/services/qr_login.py, app/routers/gestor.py and
    app/routers/admin.py's /gestor-qr endpoints, and
    mobile/src/app/qr-login.tsx).

    An already-authenticated admin generates `code` and the panel renders it
    as a QR; a gestor's phone scans it and "claims" it; the admin must then
    explicitly approve that specific claim before the phone receives a
    device_token. That human-in-the-loop approval is what keeps a code
    glimpsed or photographed by someone else from being enough on its own —
    same security property a Netflix-style TV pairing code has.

    `status` moves pending -> claimed -> approved|denied, or snaps to
    "expired" once `expires_at` passes in any unresolved state (materialized
    lazily — see resolve_status). `consumed` guards against the device_token
    being read out more than once after approval."""

    __tablename__ = "gestor_qr_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    device_token: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)

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

    # Up to 3 photos kept purely as evidence of the reading — most meters
    # aren't digital (dial-style displays where a digit can read as half one
    # number, half the next), so OCR on them was unreliable and was dropped;
    # the gestor always types the value by hand.
    foto_urls: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Marcada automáticamente cuando el consumo se sale de rango (negativo o
    # salto anormal respecto del historial). El gestor puede seguir
    # guardando la lectura igual; esto sólo la deja señalada para que un
    # admin la revise antes de facturar.
    anomala: Mapped[bool] = mapped_column(Boolean, default=False)

    # Motivo que el gestor indica cuando guarda igual una lectura que la app
    # le marcó como inusual ("Pérdida visible", "Medidor cambiado"...). Una
    # lectura con observación también queda `anomala`, para que el admin la
    # revise con ese contexto antes de facturar.
    observacion: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)

    meter: Mapped[Meter] = relationship(back_populates="readings")
    gestor: Mapped[Gestor | None] = relationship()


class Route(Base):
    """A planned walk through a set of meters (ruta de lectura), ordered by
    RouteStop.orden. Created by hand by an admin/gestor, or generated
    automatically (see app/services/routes.py). `gestor_id` is an optional
    default assignee: null means any gestor may pick it up. Editing a route
    never affects a recorrido already in progress, since starting one
    snapshots the stops into RouteRunStop."""

    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    gestor_id: Mapped[int | None] = mapped_column(ForeignKey("gestores.id"), nullable=True)
    origen: Mapped[str] = mapped_column(String(16), default="manual")  # manual | auto
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    gestor: Mapped[Gestor | None] = relationship()
    stops: Mapped[list["RouteStop"]] = relationship(
        back_populates="route", cascade="all, delete-orphan", order_by="RouteStop.orden"
    )


class RouteStop(Base):
    __tablename__ = "route_stops"
    __table_args__ = (UniqueConstraint("route_id", "meter_id", name="uq_route_stop_meter"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id"))
    orden: Mapped[int] = mapped_column()

    route: Mapped[Route] = relationship(back_populates="stops")
    meter: Mapped[Meter] = relationship()


class RouteRun(Base):
    """One gestor actually walking a Route: started from the app, advanced
    meter by meter. status: en_curso | completado | cancelado."""

    __tablename__ = "route_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"))
    gestor_id: Mapped[int] = mapped_column(ForeignKey("gestores.id"))
    status: Mapped[str] = mapped_column(String(16), default="en_curso")
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    route: Mapped[Route] = relationship()
    gestor: Mapped[Gestor] = relationship()
    stops: Mapped[list["RouteRunStop"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="RouteRunStop.orden"
    )


class RouteRunStop(Base):
    """Snapshot of one stop of a RouteRun. status: pendiente | leido |
    salteado (with `motivo`, e.g. "nadie en casa")."""

    __tablename__ = "route_run_stops"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("route_runs.id"), index=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id"))
    orden: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(16), default="pendiente")
    motivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reading_id: Mapped[int | None] = mapped_column(ForeignKey("readings.id"), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped[RouteRun] = relationship(back_populates="stops")
    meter: Mapped[Meter] = relationship()
    reading: Mapped[Reading | None] = relationship()


class ServiceCut(Base):
    """Orden de corte de servicio sobre un medidor (por impago, multa u otro
    problema). La ordena la zona administrativa, la ejecuta físicamente un
    gestor dejando evidencia, y se cierra con la reposición.

    estado: ordenado -> ejecutado -> reposicion_ordenada -> repuesto, o
    cancelado (antes de ejecutarse). Mientras esté en ordenado / ejecutado /
    reposicion_ordenada el corte está "vigente": el medidor no se lee ni
    entra en rutas nuevas (ver app/services/cuts.py). Los emails del admin se
    guardan desnormalizados para que el historial sobreviva a que el admin se
    elimine."""

    __tablename__ = "service_cuts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id"), index=True)

    motivo: Mapped[str] = mapped_column(String(16))  # impago | multa | otro
    detalle: Mapped[str | None] = mapped_column(String(500), nullable=True)
    estado: Mapped[str] = mapped_column(String(24), default="ordenado", index=True)

    ordenado_por_email: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)

    ejecutado_por_id: Mapped[int | None] = mapped_column(ForeignKey("gestores.id"), nullable=True)
    ejecutado_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    ejecucion_nota: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ejecucion_foto_urls: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    ejecucion_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    ejecucion_lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    reposicion_ordenada_por_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reposicion_ordenada_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    repuesto_por_id: Mapped[int | None] = mapped_column(ForeignKey("gestores.id"), nullable=True)
    repuesto_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    reposicion_nota: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reposicion_foto_urls: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    reposicion_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    reposicion_lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    cancelado_por_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cancelado_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    member: Mapped[Member] = relationship(back_populates="cuts")
    meter: Mapped[Meter] = relationship()
    ejecutado_por: Mapped[Gestor | None] = relationship(foreign_keys=[ejecutado_por_id])
    repuesto_por: Mapped[Gestor | None] = relationship(foreign_keys=[repuesto_por_id])
