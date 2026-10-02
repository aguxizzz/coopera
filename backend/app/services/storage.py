"""Logo storage. Uses Cloudflare R2 (S3-compatible) when configured, and
falls back to saving on local disk (served under /static) otherwise, so the
feature works out of the box before anyone sets up a bucket."""
import mimetypes
import os
import uuid

from app.config import settings

ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/svg+xml", "image/webp"}


class UnsupportedLogoType(Exception):
    pass


def _extension_for(filename: str, content_type: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext:
        return ext
    guessed = mimetypes.guess_extension(content_type) or ".bin"
    return guessed


def _r2_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def upload_logo(tenant_slug: str, kind: str, filename: str, content_type: str, data: bytes) -> str:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise UnsupportedLogoType(f"Formato no soportado: {content_type}")

    ext = _extension_for(filename, content_type)
    key = f"logos/{tenant_slug}/{kind}-{uuid.uuid4().hex}{ext}"

    if settings.r2_configured:
        client = _r2_client()
        client.put_object(
            Bucket=settings.r2_bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        base = (settings.r2_public_base_url or "").rstrip("/")
        return f"{base}/{key}"

    dest_path = os.path.join(settings.upload_dir, key)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(data)
    base = settings.public_base_url.rstrip("/")
    return f"{base}/static/{key}"


READING_PHOTO_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}


class UnsupportedPhotoType(Exception):
    pass


def upload_reading_photo(tenant_slug: str, filename: str, content_type: str, data: bytes) -> str:
    if content_type not in READING_PHOTO_CONTENT_TYPES:
        raise UnsupportedPhotoType(f"Formato no soportado: {content_type}")

    ext = _extension_for(filename, content_type)
    key = f"lecturas/{tenant_slug}/{uuid.uuid4().hex}{ext}"

    if settings.r2_configured:
        client = _r2_client()
        client.put_object(
            Bucket=settings.r2_bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        base = (settings.r2_public_base_url or "").rstrip("/")
        return f"{base}/{key}"

    dest_path = os.path.join(settings.upload_dir, key)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(data)
    base = settings.public_base_url.rstrip("/")
    return f"{base}/static/{key}"


def delete_logo(url: str) -> None:
    """Best-effort delete of a previously stored logo, given the URL that was
    returned by `upload_logo`. Silently does nothing if the URL doesn't point
    at a key we recognize, so it's safe to call with arbitrary stored URLs."""
    if not url:
        return

    if settings.r2_configured:
        base = (settings.r2_public_base_url or "").rstrip("/")
        if base and url.startswith(base + "/"):
            key = url[len(base) + 1 :]
            client = _r2_client()
            client.delete_object(Bucket=settings.r2_bucket_name, Key=key)
        return

    base = settings.public_base_url.rstrip("/")
    prefix = f"{base}/static/"
    if url.startswith(prefix):
        key = url[len(prefix) :]
        dest_path = os.path.join(settings.upload_dir, key)
        if os.path.isfile(dest_path):
            os.remove(dest_path)
