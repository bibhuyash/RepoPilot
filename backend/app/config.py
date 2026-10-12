import os

from dotenv import load_dotenv

load_dotenv()


def origins() -> list[str]:
    return [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()]


def github_token() -> str | None:
    return os.getenv("GITHUB_TOKEN") or None


def groq_model() -> str:
    return os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
