import io

from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.models import Invoice, Member, Tenant

MESES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def build_boleta_pdf(tenant: Tenant, member: Member, invoice: Invoice, saldo_total: float) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A5)
    width, height = A5

    y = height - 20 * mm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(15 * mm, y, tenant.name)
    y -= 8 * mm

    c.setFont("Helvetica", 10)
    periodo = f"{MESES[invoice.period_month]} {invoice.period_year}"
    c.drawString(15 * mm, y, f"Boleta - Periodo {periodo}")
    y -= 10 * mm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(15 * mm, y, "Datos del socio")
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    c.drawString(15 * mm, y, f"Número de socio: {member.numero_socio}")
    y -= 5 * mm
    c.drawString(15 * mm, y, f"Nombre: {member.nombre}")
    y -= 10 * mm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(15 * mm, y, "Detalle del periodo")
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    c.drawString(15 * mm, y, f"Consumo: {invoice.consumo}")
    y -= 5 * mm
    c.drawString(15 * mm, y, f"Monto del periodo: ${invoice.monto:,.2f}")
    y -= 5 * mm
    if invoice.vencimiento:
        c.drawString(15 * mm, y, f"Vencimiento: {invoice.vencimiento.strftime('%d/%m/%Y')}")
        y -= 5 * mm
    y -= 5 * mm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(15 * mm, y, f"Saldo total adeudado: ${saldo_total:,.2f}")
    y -= 10 * mm

    if tenant.mp_alias:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(15 * mm, y, "Pagá por Mercado Pago con el alias:")
        y -= 6 * mm
        c.setFont("Helvetica", 11)
        c.drawString(15 * mm, y, tenant.mp_alias)

    c.showPage()
    c.save()
    return buffer.getvalue()
