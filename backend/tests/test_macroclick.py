import base64

import pytest
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.services import macroclick as mc


def _aes_decrypt(cipher_b64: str, secret_key: str) -> str:
    """Decrypt what `_aes_encrypt` produces, to assert round-trips without
    depending on the PHP reference implementation being reachable."""
    key = mc._pad_key(secret_key)
    raw = base64.b64decode(cipher_b64)
    iv, ciphertext = raw[:16], raw[16:]
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = sym_padding.PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode()


def test_encrypt_decrypt_roundtrip():
    secret = "super-secret-token"
    encrypted = mc._encrypt(secret)
    assert encrypted != secret
    assert mc._decrypt(encrypted) == secret


def test_aes_encrypt_roundtrips_with_short_key():
    assert _aes_decrypt(mc._aes_encrypt("hola mundo", "short"), "short") == "hola mundo"


def test_aes_encrypt_roundtrips_with_long_key():
    long_key = "a" * 50
    assert _aes_decrypt(mc._aes_encrypt("12345", long_key), long_key) == "12345"


def test_aes_encrypt_is_not_deterministic():
    # Random IV each time -> same plaintext/key produce different ciphertext.
    a = mc._aes_encrypt("same", "key")
    b = mc._aes_encrypt("same", "key")
    assert a != b


def test_sha256_hash_is_deterministic():
    h1 = mc._sha256_hash("1.2.3.4", "comercio1", "0000000000", "450000", "secret")
    h2 = mc._sha256_hash("1.2.3.4", "comercio1", "0000000000", "450000", "secret")
    assert h1 == h2
    assert len(h1) == 64  # hex sha256


def test_base_url_sandbox_by_default(tenant):
    assert mc._base_url(tenant) == mc.MACROCLICK_SANDBOX_BASE


def test_base_url_production(tenant):
    tenant.macroclick_environment = "production"
    assert mc._base_url(tenant) == mc.MACROCLICK_PROD_BASE


def test_save_credentials_encrypts_and_stores(db_session, tenant):
    mc.save_credentials(db_session, tenant, "comercio-1", "0000000000", "secret-xyz", "production")

    assert tenant.macroclick_comercio_id == "comercio-1"
    assert tenant.macroclick_sucursal == "0000000000"
    assert mc._decrypt(tenant.macroclick_secret_key) == "secret-xyz"
    assert tenant.macroclick_environment == "production"


def test_disconnect_tenant_clears_fields(db_session, tenant):
    mc.save_credentials(db_session, tenant, "comercio-1", "0000000000", "secret-xyz", "production")
    mc.disconnect_tenant(db_session, tenant)

    assert tenant.macroclick_comercio_id is None
    assert tenant.macroclick_sucursal is None
    assert tenant.macroclick_secret_key is None
    assert tenant.macroclick_environment == "sandbox"


def test_build_checkout_form_html_requires_connection(member, invoice, tenant):
    with pytest.raises(mc.MacroclickError):
        mc.build_checkout_form_html(tenant, member, invoice, client_ip="1.2.3.4")


def test_build_checkout_form_html_contains_expected_fields(db_session, tenant, member, invoice):
    mc.save_credentials(db_session, tenant, "comercio-1", "0000000000", "secret-xyz", "sandbox")

    html = mc.build_checkout_form_html(tenant, member, invoice, client_ip="1.2.3.4")

    assert mc.MACROCLICK_SANDBOX_BASE in html
    assert 'name="Comercio" value="comercio-1"' in html
    assert f'name="TransaccionComercioId" value="{invoice.id}-' in html
    assert "<script>" in html


def test_build_checkout_token_roundtrip(tenant, invoice):
    token = mc.build_checkout_token(tenant.slug, invoice.id)
    slug, invoice_id = mc.read_checkout_token(token)
    assert slug == tenant.slug
    assert invoice_id == invoice.id


def test_read_checkout_token_rejects_garbage():
    with pytest.raises(mc.MacroclickError):
        mc.read_checkout_token("not-a-real-token")


def test_process_webhook_payment_marks_invoice_paid(db_session, tenant, invoice):
    result = mc.process_webhook_payment(
        db_session, tenant, {"TransaccionComercioId": f"{invoice.id}-171234", "EstadoId": 3}
    )
    assert result.id == invoice.id
    assert result.pagado is True


def test_process_webhook_payment_ignores_other_states(db_session, tenant, invoice):
    result = mc.process_webhook_payment(
        db_session, tenant, {"TransaccionComercioId": f"{invoice.id}-171234", "EstadoId": 7}
    )
    assert result.pagado is False


def test_process_webhook_payment_unknown_invoice_returns_none(db_session, tenant):
    result = mc.process_webhook_payment(
        db_session, tenant, {"TransaccionComercioId": "999999-171234", "EstadoId": 3}
    )
    assert result is None


def test_process_webhook_payment_missing_transaccion_id_returns_none(db_session, tenant):
    result = mc.process_webhook_payment(db_session, tenant, {"EstadoId": 3})
    assert result is None
