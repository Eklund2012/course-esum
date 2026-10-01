from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "Course Evaluation Summarizer Service"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = False
    
    # Security
    API_KEY: str = "dev-secret-key-12345"
    API_KEY_HEADER: str = "X-API-Key"
    
    # Gemini AI
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Gemini retry / rate-limit settings
    GEMINI_MAX_RETRIES: int = 4         # Maximum number of retry attempts
    GEMINI_BASE_DELAY_MS: int = 500     # Initial backoff delay in milliseconds
    GEMINI_MAX_DELAY_MS: int = 30_000   # Maximum backoff delay cap in milliseconds
    
    # Persistence
    DATABASE_URL: str = "sqlite:///./course_esum.db"
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: str = "60/minute"
    
    # Max reports to fetch/analyze by default
    DEFAULT_MAX_REPORTS: int = 3
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

@lru_cache()
def get_settings() -> Settings:
    return Settings()
