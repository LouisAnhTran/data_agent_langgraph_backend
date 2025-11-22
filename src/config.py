from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # LLM API Keys
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    # LangChain Settings
    langchain_tracing_v2: bool = False
    langchain_api_key: Optional[str] = None
    langchain_project: Optional[str] = None

    # Application Settings
    app_name: str = "Data Agent LangGraph"
    app_version: str = "0.1.0"
    debug: bool = False

    # API Settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Data Processing Settings
    max_data_rows: int = 10000
    default_llm_temperature: float = 0.7
    default_llm_model: str = "gpt-4o"

# Create a global settings instance
settings = Settings()
