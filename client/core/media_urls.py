from urllib.parse import parse_qsl, urlparse, urlunparse

from core.config import settings


_SIGNED_URL_KEYS = {
    "x-amz-algorithm",
    "x-amz-credential",
    "x-amz-date",
    "x-amz-expires",
    "x-amz-security-token",
    "x-amz-signature",
    "x-amz-signedheaders",
    "awsaccesskeyid",
    "expires",
    "signature",
}


def _public_bucket_url(key: str) -> str:
    protocol = "https" if settings.MINIO_SECURE else "http"
    normalized_key = key.lstrip("/")
    if normalized_key.startswith(f"{settings.MINIO_BUCKET}/"):
        normalized_key = normalized_key[len(settings.MINIO_BUCKET) + 1 :]
    return f"{protocol}://{settings.MINIO_ENDPOINT}/{settings.MINIO_BUCKET}/{normalized_key}"


def normalize_media_url(value: str | None) -> str | None:
    if value is None:
        return None

    raw = value.strip()
    if not raw:
        return None

    parsed = urlparse(raw)

    # Allow callers to pass the object key instead of a full public URL.
    if not parsed.scheme and not parsed.netloc and "/" in parsed.path:
        return _public_bucket_url(parsed.path)

    if not parsed.scheme or not parsed.netloc:
        return raw

    query_keys = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    if query_keys & _SIGNED_URL_KEYS:
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

    if parsed.netloc == settings.MINIO_ENDPOINT:
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

    return raw


def normalize_media_urls(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for value in values or []:
        cleaned = normalize_media_url(value)
        if cleaned:
            normalized.append(cleaned)
    return normalized
