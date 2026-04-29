from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )
    
    APP_NAME: str = "LLM Collapse Detector"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"
    
    DATABASE_URL: str
    
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ENFORCE_HTTPS: bool = False
    PUBLIC_REGISTRATION_ENABLED: bool = True
    BOOTSTRAP_ADMIN_TOKEN: str = ""

    ACCESS_COOKIE_NAME: str = "llm_access_token"
    REFRESH_COOKIE_NAME: str = "llm_refresh_token"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    COOKIE_DOMAIN: str = ""

    ENCRYPT_DATA: bool = False
    DATA_ENCRYPTION_KEY: str = ""
    
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@llmdetector.com"
    ALERT_EMAIL_RECIPIENTS: List[str] = []

    HUGGINGFACE_HUB_TOKEN: str = ""
    BENCHMARK_MAX_REMOTE_MODEL_SIZE_GB: int = 8
    BENCHMARK_MAX_REMOTE_WEIGHT_SHARDS: int = 4
    
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    
    MAX_PROMPT_LENGTH: int = 10000
    MAX_OUTPUT_LENGTH: int = 50000
    MAX_BATCH_SIZE: int = 100
    MAX_TOKENS_TO_STORE: int = 1000
    
    DEFAULT_ALERT_THRESHOLD_ENTROPY: float = 0.5
    DEFAULT_ALERT_THRESHOLD_KL_DIVERGENCE: float = 0.3
    DEFAULT_ALERT_THRESHOLD_LENGTH_DEVIATION: float = 2.0
    
    UPLOAD_DIR: str = "./uploads"
    EXPORT_DIR: str = "./exports"
    MAX_UPLOAD_SIZE_MB: int = 100

    EVAL_MAX_PROMPTS_PER_JOB: int = 2000
    EVAL_MODEL_LOCK_TTL_SECONDS: int = 7200
    EVAL_DEFAULT_TOP_K_TOKEN_PROBS: int = 10
    EVAL_MAX_TOP_K_TOKEN_PROBS: int = 50
    

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
