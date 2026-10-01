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


class AuditLogOut(BaseModel):
    id: int
    actor_type: str
    actor_email: str
    action: str
    target: str | None
    details: str | None
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)
