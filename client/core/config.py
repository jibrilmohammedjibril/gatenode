import logging
from pydantic_settings import BaseSettings
from typing import Optional

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    PROJECT_NAME: str = "Gatenode Resident Client"
    
    # Database
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = "gatenode"
    DATABASE_URL: Optional[str] = None
    PUBLIC_WEB_APP_URL: Optional[str] = "https://gatenode.app"
    
    # Auth
    SECRET_KEY: Optional[str] = None
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    REFRESH_TOKEN_EXPIRE_MINUTES: int = 10080 # 7 days

    # Nomba
    NOMBA_CLIENT_ID: Optional[str] = None
    NOMBA_CLIENT_SECRET: Optional[str] = None
    NOMBA_ACCOUNT_ID: Optional[str] = None
    NOMBA_BASE_URL: str = "https://api.nomba.com"
    NOMBA_WEBHOOK_SECRET: Optional[str] = None
    SERVICE_CHARGE_REVENUE_ACCOUNT_ID: Optional[str] = None
    SERVICE_CHARGE_DEFAULT_MONTHLY_FEE_KOBO: int = 100_000

    # MinIO
    MINIO_ENDPOINT: str = "images.gatenode.com"
    MINIO_ACCESS_KEY: Optional[str] = None
    MINIO_SECRET_KEY: Optional[str] = None
    MINIO_BUCKET: str = "gatenode-uploads"
    MINIO_SECURE: bool = True
    
    # Email
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAIL_FROM_EMAIL: Optional[str] = "noreply@gatenode.com"
    EMAIL_FROM_NAME: Optional[str] = "Resident Client"
    
    # ZeptoMail
    ZEPTOMAIL_API_KEY: Optional[str] = None
    ZEPTOMAIL_API_URL: str = "https://api.zeptomail.com/v1.1/email"
    
    # WhatsApp (Meta)
    WHATSAPP_API_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    
    # Firebase Cloud Messaging
    FIREBASE_CREDENTIALS: Optional[str] = None
    
    # Apple APNs (Direct)
    APPLE_TEAM_ID: Optional[str] = None
    APPLE_KEY_ID: Optional[str] = None
    APPLE_BUNDLE_ID: Optional[str] = "com.gatenode.app"
    APPLE_P8_PATH: Optional[str] = None # Path to .p8 file or content
    APPLE_USE_SANDBOX: bool = False
    
    # Fez Delivery
    FEZ_DELIVERY_SECRET_KEY: Optional[str] = None
    FEZ_DELIVERY_BASE_URL: str = "https://apisandbox.fezdelivery.co/v1"
    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+asyncpg://", 1)
            elif url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            
            # Fix: asyncpg does not support 'sslmode', it uses 'ssl'
            if "sslmode=" in url:
                url = url.replace("sslmode=require", "ssl=require")
                url = url.replace("sslmode=disable", "ssl=disable")
                url = url.replace("sslmode=prefer", "ssl=prefer")

            return url
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    class Config:
        env_file = ("client/.env", ".env")
        extra = "ignore"

settings = Settings()


def validate_startup_settings() -> None:
    missing = []

    required = {
        "SECRET_KEY": settings.SECRET_KEY,
    }

    for name, value in required.items():
        if not value:
            missing.append(name)

    if settings.MINIO_ACCESS_KEY or settings.MINIO_SECRET_KEY:
        minio_missing = []
        if not settings.MINIO_ACCESS_KEY:
            minio_missing.append("MINIO_ACCESS_KEY")
        if not settings.MINIO_SECRET_KEY:
            minio_missing.append("MINIO_SECRET_KEY")
        if minio_missing:
            logger.warning(
                "MinIO is partially configured; file uploads will be unavailable until %s is set.",
                ", ".join(minio_missing),
            )

    nomba_values = {
        "NOMBA_CLIENT_ID": settings.NOMBA_CLIENT_ID,
        "NOMBA_CLIENT_SECRET": settings.NOMBA_CLIENT_SECRET,
        "NOMBA_ACCOUNT_ID": settings.NOMBA_ACCOUNT_ID,
    }
    if any(nomba_values.values()) and not all(nomba_values.values()):
        missing_nomba = ", ".join(name for name, value in nomba_values.items() if not value)
        logger.warning(
            "Nomba is partially configured; wallet funding and transfers will be unavailable until %s is set.",
            missing_nomba,
        )

    apns_values = {
        "APPLE_TEAM_ID": settings.APPLE_TEAM_ID,
        "APPLE_KEY_ID": settings.APPLE_KEY_ID,
        "APPLE_P8": settings.APPLE_P8_PATH or getattr(settings, "APPLE_P8_KEY", None),
    }
    if any(apns_values.values()) and not all(apns_values.values()):
        missing_apns = ", ".join(name for name, value in apns_values.items() if not value)
        logger.warning(
            "APNs is partially configured; push delivery will be unavailable until %s is set.",
            missing_apns,
        )

    if missing:
        missing_list = ", ".join(sorted(set(missing)))
        raise RuntimeError(f"Missing required client settings: {missing_list}")
