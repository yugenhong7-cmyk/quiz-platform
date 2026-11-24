"""应用配置：从环境变量 / .env 读取。"""
import os
from functools import lru_cache

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


class Settings:
    APP_NAME: str = "AI 智能题库与刷题平台"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production-please")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./quiz_platform.db")

    AI_API_BASE: str = os.getenv("AI_API_BASE", "https://api.openai.com/v1")
    AI_API_KEY: str = os.getenv("AI_API_KEY", "")
    AI_MODEL: str = os.getenv("AI_MODEL", "gpt-4o-mini")
    AI_TIMEOUT: int = int(os.getenv("AI_TIMEOUT", "60"))
    AI_MAX_TOKENS: int = int(os.getenv("AI_MAX_TOKENS", "2048"))

    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "20"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
