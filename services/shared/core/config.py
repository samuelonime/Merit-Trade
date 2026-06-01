from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_ENV: str = "development"
    APP_NAME: str = "MeritTradeAI"
    SECRET_KEY: str
    DEBUG: bool = False

    # Database
    DATABASE_URL: str
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "merittrade"

    # Redis
    REDIS_URL: str
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str

    # Celery
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # AES
    AES_ENCRYPTION_KEY: str  # must be 32 bytes (base64 encoded)

    # Anthropic (strictly limited use)
    ANTHROPIC_API_KEY: str
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # Services
    AUTH_SERVICE_URL: str = "http://auth-service:8001"
    USER_SERVICE_URL: str = "http://user-service:8002"
    SIGNAL_ENGINE_URL: str = "http://signal-engine:8003"
    MARKET_DATA_URL: str = "http://market-data:8004"
    EXECUTION_ENGINE_URL: str = "http://execution-engine:8005"
    RISK_ENGINE_URL: str = "http://risk-engine:8006"
    NOTIFICATION_SERVICE_URL: str = "http://notification-service:8007"
    ADMIN_SERVICE_URL: str = "http://admin-service:8008"

    # Risk Defaults
    DEFAULT_MAX_RISK_PER_TRADE: float = 0.02
    DEFAULT_MAX_DAILY_LOSS: float = 0.05
    DEFAULT_MAX_DRAWDOWN: float = 0.15
    MIN_CONFIDENCE_THRESHOLD: int = 65

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 120

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    # Payments
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    PAYSTACK_SECRET_KEY: Optional[str] = None
    PAYSTACK_PUBLIC_KEY: Optional[str] = None

    # Market Data Providers
    # Twelve Data — forex + gold OHLCV (free tier: 800 requests/day)
    # Sign up at https://twelvedata.com
    TWELVE_DATA_API_KEY: Optional[str] = None

    # Notifications
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    SENDGRID_API_KEY: Optional[str] = None
    EMAIL_FROM: str = "noreply@merittrade.ai"
    VAPID_PUBLIC_KEY: Optional[str] = None
    VAPID_PRIVATE_KEY: Optional[str] = None

    # ML Models
    MODEL_XGBOOST_PATH: str = "/app/models/xgboost_v1.json"
    MODEL_LSTM_PATH: str = "/app/models/lstm_v1.pt"
    MODEL_TRANSFORMER_PATH: str = "/app/models/transformer_v1.pt"
    MODEL_SCALER_PATH: str = "/app/models/scaler_v1.pkl"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
