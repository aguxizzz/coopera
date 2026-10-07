import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TenantPublic(BaseModel):
    slug: str
    name: str
    primary_color: str
    contact_email: str | None
    contact_phone: str | None
    contact_whatsapp: str | None
    contact_address: str | None
    logo_primary_url: str | None
    logo_secondary_url: str | None

    model_config = ConfigDict(from_attributes=True)


class TenantSettingsOut(TenantPublic):
    pass


class TenantSettingsUpdate(BaseModel):
    contact_email: str | None = None
    contact_phone: str | None = None
    contact_whatsapp: str | None = None
    contact_address: str | None = None
    primary_color: str | None = None


class AdminLogin(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class GestorTokenResponse(TokenResponse):
    refresh_token: str


class GestorRefreshRequest(BaseModel):
    refresh_token: str


class GestorDeviceLogin(BaseModel):
    password: str


class GestorProfileOut(BaseModel):
    id: int
    nombre: str


class GestorDeviceLoginResponse(BaseModel):
    device_token: str
    profiles: list[GestorProfileOut]


class GestorSelectProfile(BaseModel):
    device_token: str
    gestor_id: int


QrStatus = Literal["pending", "claimed", "approved", "denied", "expired"]


class GestorQrStartOut(BaseModel):
    code: str
    expires_at: dt.datetime


class GestorQrAdminStatusOut(BaseModel):
    status: QrStatus
    expires_at: dt.datetime


class GestorQrClaimOut(BaseModel):
    status: QrStatus


class GestorQrPollOut(BaseModel):
    status: QrStatus
    device_token: str | None = None
    profiles: list[GestorProfileOut] | None = None


class MemberLookupRequest(BaseModel):
    numero_socio: str
    identificador: str


class InvoiceOut(BaseModel):
    id: int
    period_year: int
    period_month: int
    consumo: float
    monto: float
    vencimiento: dt.date | None
    pagado: bool

    model_config = ConfigDict(from_attributes=True)


class UpdateInvoicePagado(BaseModel):
    pagado: bool


class MemberAccountOut(BaseModel):
    numero_socio: str
    nombre: str
    saldo_total: float
    ultima_factura: InvoiceOut | None
    historial: list[InvoiceOut]
    mp_alias: str | None
    mp_cbu: str | None
    mp_titular: str | None
    mp_connected: bool
    helipagos_connected: bool
    macroclick_connected: bool


class PayInvoiceRequest(BaseModel):
    numero_socio: str
    identificador: str


class PayInvoiceResponse(BaseModel):
    init_point: str


class MpStatusOut(BaseModel):
    configured: bool
    connected: bool
    mp_user_id: str | None


class MpConnectUrlOut(BaseModel):
    url: str


class HelipagosStatusOut(BaseModel):
    connected: bool
    environment: str


class HelipagosConnectRequest(BaseModel):
    token: str
    webhook_apikey: str
    environment: Literal["sandbox", "production"] = "sandbox"


class MacroclickStatusOut(BaseModel):
    connected: bool
    environment: str


class MacroclickConnectRequest(BaseModel):
    comercio_id: str
    sucursal: str = "0000000000"
    secret_key: str
    environment: Literal["sandbox", "production"] = "sandbox"


class MemberRow(BaseModel):
    id: int
    numero_socio: str
    nombre: str
    identificador: str
    saldo_total: float

    model_config = ConfigDict(from_attributes=True)


class ImportResult(BaseModel):
    period_year: int
    period_month: int
    rows_processed: int
    members_created: int
    members_updated: int


class DeleteMembersRequest(BaseModel):
    member_ids: list[int]


class DeleteMembersResult(BaseModel):
    deleted: int


class PlatformLogin(BaseModel):
    email: str
    password: str


class PdfProfileIn(BaseModel):
    field_patterns: dict[str, str]


class PdfProfileOut(BaseModel):
    tenant_id: int
    field_patterns: dict[str, str]
    updated_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class PdfProfilePreviewPage(BaseModel):
    page: int
    raw_text: str
    fields: dict[str, str | None]


class PdfImportJobOut(BaseModel):
    id: int
    status: str
    total_pages: int
    processed_pages: int
    error: str | None
    import_batch_id: int | None

    model_config = ConfigDict(from_attributes=True)


class TenantSummary(BaseModel):
    id: int
    slug: str
    name: str
    admin_count: int
    member_count: int
    created_at: dt.datetime


class TenantCreate(BaseModel):
    slug: str
    name: str
    admin_email: str
    admin_password: str
    mp_alias: str | None = None
    mp_cbu: str | None = None
    mp_titular: str | None = None
    primary_color: str = "#2563eb"


class AdminUserOut(BaseModel):
    id: int
    email: str
    role: str
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class AdminCreate(BaseModel):
    email: str
    password: str
    role: Literal["owner", "staff"] = "staff"


class AdminPasswordReset(BaseModel):
    password: str


class AdminRoleUpdate(BaseModel):
    role: Literal["owner", "staff"]


class GestorOut(BaseModel):
    id: int
    nombre: str
    email: str
    activo: bool
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class GestorCreate(BaseModel):
    nombre: str
    email: str


class GestorActivoUpdate(BaseModel):
    activo: bool


class GestorSharedPasswordUpdate(BaseModel):
    password: str


class MeterOut(BaseModel):
    id: int
    codigo: str
    tipo: str
    direccion: str | None
    unidad: str
    activo: bool
    member_id: int
    numero_socio: str
    nombre_socio: str
    ultima_lectura: float | None
    ultima_lectura_fecha: dt.datetime | None
    ultima_lectura_anomala: bool = False
    ultima_lectura_id: int | None = None


class MeterCreate(BaseModel):
    member_id: int
    codigo: str
    tipo: Literal["luz", "agua", "gas"] = "luz"
    direccion: str | None = None
    unidad: str = "kWh"


class ReadingCreate(BaseModel):
    valor: float
    lat: float | None = None
    lon: float | None = None


class ReadingOut(BaseModel):
    id: int
    meter_id: int
    valor: float
    valor_anterior: float | None
    consumo: float | None
    foto_urls: list[str] | None
    anomala: bool
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogOut(BaseModel):
    id: int
    actor_type: str
    actor_email: str
    action: str
    target: str | None
    details: str | None
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


# --- Rutas de lectura -------------------------------------------------------


class RouteStopOut(BaseModel):
    meter_id: int
    orden: int
    codigo: str
    tipo: str
    direccion: str | None
    nombre_socio: str


class RouteOut(BaseModel):
    # id is None only for the dry-run output of auto-generation.
    id: int | None
    nombre: str
    gestor_id: int | None
    gestor_nombre: str | None
    origen: str
    activo: bool
    cantidad_medidores: int
    # Auto-generation only: how many past jornadas this route was inferred
    # from (null for routes built from address order, and for stored routes).
    recorridos_base: int | None = None
    paradas: list[RouteStopOut]


class RouteCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    meter_ids: list[int]
    gestor_id: int | None = None


class RouteUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    meter_ids: list[int] | None = None
    # Explicit null unassigns the route, so this one is checked through
    # model_fields_set rather than "is not None".
    gestor_id: int | None = None
    activo: bool | None = None


class RouteAutoGenerate(BaseModel):
    tipo: Literal["luz", "agua", "gas"] | None = None
    # A pause longer than this between two readings of the same gestor ends
    # one jornada and starts the next.
    gap_horas: float = Field(default=4, ge=1, le=12)
    # Jornadas with fewer meters than this are ignored as noise.
    min_medidores: int = Field(default=5, ge=1, le=500)
    meses_historial: int = Field(default=3, ge=1, le=24)
    # Also build routes (by address) for meters no past jornada covers.
    incluir_sin_historial: bool = True
    # Size of those address-based routes.
    meters_por_ruta: int = Field(default=30, ge=1, le=500)
    # Leave out meters already read in the current calendar month.
    solo_pendientes: bool = False
    gestor_id: int | None = None
    nombre_base: str = Field(default="Ruta", min_length=1, max_length=100)
    # When true nothing is saved; the proposed routes are just returned.
    preview: bool = False


class RunStopOut(BaseModel):
    id: int
    orden: int
    status: str
    motivo: str | None
    meter_id: int
    codigo: str
    tipo: str
    direccion: str | None
    unidad: str
    numero_socio: str
    nombre_socio: str
    # Latest reading of the meter that isn't this stop's own: what the gestor
    # compares against. `ultima_lectura_fecha`/`_id` let the app notice the
    # meter was already read this month (e.g. from the Ruta tab).
    ultima_lectura: float | None
    ultima_lectura_fecha: dt.datetime | None = None
    ultima_lectura_id: int | None = None
    reading_id: int | None
    # Value of the reading this very stop produced (null until it is read).
    valor_leido: float | None = None
    completed_at: dt.datetime | None


class RunOut(BaseModel):
    id: int
    route_id: int
    route_nombre: str
    gestor_id: int
    gestor_nombre: str
    status: str
    started_at: dt.datetime
    finished_at: dt.datetime | None
    total: int
    leidas: int
    salteadas: int
    pendientes: int
    siguiente: RunStopOut | None
    paradas: list[RunStopOut] | None = None


class RunSkip(BaseModel):
    motivo: str | None = Field(default=None, max_length=255)


class RunStopResult(BaseModel):
    run: RunOut
    reading: ReadingOut | None = None
