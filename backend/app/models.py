import datetime as dt

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
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
    primary_color: Mapped[str] = mapped_column(String(16), default="#2563eb")
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
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    tenant: Mapped[Tenant] = relationship(back_populates="admins")


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
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    member: Mapped[Member] = relationship(back_populates="invoices")
