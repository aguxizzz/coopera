import datetime as dt

from pydantic import BaseModel, ConfigDict


class TenantPublic(BaseModel):
    slug: str
    name: str
    primary_color: str

    model_config = ConfigDict(from_attributes=True)


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
    period_year: int
    period_month: int
    consumo: float
    monto: float
    vencimiento: dt.date | None
    pagado: bool

    model_config = ConfigDict(from_attributes=True)


class MemberAccountOut(BaseModel):
    numero_socio: str
    nombre: str
    saldo_total: float
    ultima_factura: InvoiceOut | None
    historial: list[InvoiceOut]
    mp_alias: str | None


class MemberRow(BaseModel):
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
