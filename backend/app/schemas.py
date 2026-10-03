import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict


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
    ocr_valor: str | None = None
    ocr_confianza: float | None = None


class ReadingOut(BaseModel):
    id: int
    meter_id: int
    valor: float
    valor_anterior: float | None
    consumo: float | None
    foto_url: str | None
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
