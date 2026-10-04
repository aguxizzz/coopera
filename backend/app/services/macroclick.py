"""Macro Click de Pago (Banco Macro) - integración NO OFICIAL.

⚠️ A diferencia de Mercado Pago y Helipagos, no existe documentación pública
de la API de Macro Click de Pago. Todo lo que sigue se reconstruyó leyendo un
plugin de WooCommerce de terceros que integra el mismo gateway (ver
`macroclick/reference-woocommerce-plugin.php` y `macroclick/plan.md` en la
raíz del repo) — no es un producto de Banco Macro ni fue validado con ellos.
Antes de ir a producción, confirmar con el ejecutivo de cuenta del banco:
nombres exactos de los campos del webhook, si hay alguna firma/secreto para
validarlo (acá no se valida nada, ver `app/routers/macroclick.py`), y si
`EstadoId` tiene otros valores además de los que aparecen en el plugin.

A diferencia de las otras dos integraciones (API REST que devuelve una URL de
checkout), Macro Click de Pago funciona con un <form> HTML que el comercio
arma con algunos campos cifrados y auto-envía por POST directo al dominio de
Macro ("botón integrado"). No hay llamada previa que devuelva una URL: el
checkout_url lo servimos nosotros mismos (`build_checkout_form_html`), y el
navegador del socio termina ahí.

Flow:

1. Admin pega IdComercio / Sucursal / SecretKey -> `save_credentials` los
   guarda (SecretKey cifrada, mismo esquema Fernet que `helipagos.py`).
2. `build_checkout_form_html` arma el form auto-submit para una factura.
3. Macro llama al webhook del tenant -> `process_webhook_payment` matchea la
   factura por el `TransaccionComercioId` que nosotros generamos y la marca
   pagada según `EstadoId`.
"""
import base64
import datetime as dt
import hashlib
import html
import os
import time

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Invoice, Member, Tenant

MACROCLICK_SANDBOX_BASE = "https://sandboxpp.asjservicios.com.ar/"
MACROCLICK_PROD_BASE = "https://botonpp.macroclickpago.com.ar/"

CHECKOUT_TOKEN_AUDIENCE = "macroclick_checkout"

# EstadoId tal como aparecen en el plugin de referencia (no confirmado con
# Banco Macro). 3 = pago confirmado; 2/10 = procesando; 7/8/11/4 = cancelado
# o vencido; 5/6 = error de hash.
PAID_STATES = {3}


class MacroclickError(Exception):
    pass


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret.encode()).digest())
    return Fernet(key)


def _encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()


def _base_url(tenant: Tenant) -> str:
    return MACROCLICK_PROD_BASE if tenant.macroclick_environment == "production" else MACROCLICK_SANDBOX_BASE


def save_credentials(
    db: Session, tenant: Tenant, comercio_id: str, sucursal: str, secret_key: str, environment: str
) -> None:
    tenant.macroclick_comercio_id = comercio_id
    tenant.macroclick_sucursal = sucursal
    tenant.macroclick_secret_key = _encrypt(secret_key)
    tenant.macroclick_environment = environment
    db.commit()


def disconnect_tenant(db: Session, tenant: Tenant) -> None:
    tenant.macroclick_comercio_id = None
    tenant.macroclick_sucursal = None
    tenant.macroclick_secret_key = None
    tenant.macroclick_environment = "sandbox"
    db.commit()


def _pad_key(secret_key: str) -> bytes:
    """Puerto del padding de clave del plugin PHP de referencia: repetir hasta
    >=32 bytes y truncar a 32 (AES-256 necesita una clave de 32 bytes)."""
    phrase = secret_key
    while len(phrase) < 32:
        phrase += phrase
    return phrase[:32].encode()


def _aes_encrypt(plain_text: str, secret_key: str) -> str:
    key = _pad_key(secret_key)
    iv = os.urandom(16)
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(plain_text.encode()) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(iv + ciphertext).decode()


def _sha256_hash(ip_address: str, comercio: str, sucursal: str, amount: str, secret_key: str) -> str:
    raw = f"{ip_address}*{comercio}*{sucursal}*{amount}*{secret_key}"
    return hashlib.sha256(raw.encode()).hexdigest()


def build_checkout_token(tenant_slug: str, invoice_id: int) -> str:
    """Token de corta duración que autoriza a `checkout-form` a servir el
    formulario de pago sin volver a pedirle numero_socio/identificador al
    socio (ya se validaron en el endpoint `pay-macroclick`)."""
    expire = dt.datetime.utcnow() + dt.timedelta(minutes=10)
    payload = {
        "aud": CHECKOUT_TOKEN_AUDIENCE,
        "tenant_slug": tenant_slug,
        "invoice_id": invoice_id,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def read_checkout_token(token: str) -> tuple[str, int]:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=["HS256"], audience=CHECKOUT_TOKEN_AUDIENCE
        )
    except JWTError as exc:
        raise MacroclickError("El link de pago venció, volvé a intentarlo") from exc
    return payload["tenant_slug"], payload["invoice_id"]


def build_checkout_form_html(tenant: Tenant, member: Member, invoice: Invoice, client_ip: str) -> str:
    if not tenant.macroclick_comercio_id or not tenant.macroclick_secret_key:
        raise MacroclickError("Esta cooperativa todavía no conectó Macro Click de Pago")

    secret_key = _decrypt(tenant.macroclick_secret_key)
    comercio = tenant.macroclick_comercio_id
    sucursal = tenant.macroclick_sucursal or "0000000000"
    amount = str(int(round(float(invoice.monto) * 100)))
    transaccion_id = f"{invoice.id}-{int(time.time())}"
    descripcion = f"{tenant.name} - Factura #{invoice.id} - Socio {member.numero_socio}"[:128]

    callback_success = f"{settings.frontend_base_url.rstrip('/')}/{tenant.slug}?pago=exito"
    callback_cancel = f"{settings.frontend_base_url.rstrip('/')}/{tenant.slug}?pago=cancelado"

    fields = {
        "Comercio": comercio,
        "SucursalComercio": _aes_encrypt(sucursal, secret_key),
        "TransaccionComercioId": transaccion_id,
        "Monto": _aes_encrypt(amount, secret_key),
        "CallbackSuccess": _aes_encrypt(callback_success, secret_key),
        "CallbackCancel": _aes_encrypt(callback_cancel, secret_key),
        "Producto[0]": descripcion,
        "Hash": _sha256_hash(client_ip, comercio, sucursal, amount, secret_key),
    }

    inputs = "".join(
        f'<input type="hidden" name="{html.escape(name)}" value="{html.escape(value)}">'
        for name, value in fields.items()
    )
    action = html.escape(_base_url(tenant))
    return (
        "<!doctype html><html><body>"
        f'<form id="macroclick-form" action="{action}" method="post">{inputs}</form>'
        "<script>document.getElementById('macroclick-form').submit();</script>"
        "</body></html>"
    )


def process_webhook_payment(db: Session, tenant: Tenant, payload: dict) -> Invoice | None:
    transaccion_id = payload.get("TransaccionComercioId")
    if not transaccion_id:
        return None

    try:
        invoice_id = int(str(transaccion_id).split("-")[0])
    except ValueError:
        return None

    invoice = (
        db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.tenant_id == tenant.id).first()
    )
    if invoice is None:
        return None

    try:
        estado_id = int(payload.get("EstadoId"))
    except (TypeError, ValueError):
        return invoice

    if estado_id in PAID_STATES:
        invoice.pagado = True
    db.commit()
    return invoice
