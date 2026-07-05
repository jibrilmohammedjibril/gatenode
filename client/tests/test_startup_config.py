from core.config import settings, validate_startup_settings


def test_startup_validation_allows_optional_integrations_missing(monkeypatch):
    monkeypatch.setattr(settings, "MINIO_ACCESS_KEY", None, raising=False)
    monkeypatch.setattr(settings, "MINIO_SECRET_KEY", None, raising=False)
    monkeypatch.setattr(settings, "NOMBA_CLIENT_ID", None, raising=False)
    monkeypatch.setattr(settings, "NOMBA_CLIENT_SECRET", None, raising=False)
    monkeypatch.setattr(settings, "NOMBA_ACCOUNT_ID", None, raising=False)

    validate_startup_settings()
