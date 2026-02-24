"""Configuration settings for the HIPAA De-identification API."""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # LLM Provider: "openai" or "azure"
    llm_provider: str = "openai"

    # OpenAI settings (used when llm_provider == "openai")
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_temperature: float = -1.0  # -1 means "use model default" (omit param)

    # Azure OpenAI settings (used when llm_provider == "azure")
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment_name: str = ""
    azure_openai_api_version: str = "2024-02-15-preview"

    # OCR settings
    ocr_enabled: bool = True

    # De-identification mode: "mask", "placeholder", or "synthetic"
    deidentification_mode: str = "placeholder"

    # Storage settings
    storage_dir: Path = Path("/tmp/hipaa-deidentification-storage")
    max_file_size_mb: int = 50

    # CORS settings
    cors_origins: str = "*"

    # Rate limiting
    rate_limit: str = "100/minute"

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    @property
    def max_file_size_bytes(self) -> int:
        """Maximum file size in bytes."""
        return self.max_file_size_mb * 1024 * 1024

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


# Global settings instance
settings: Optional[Settings] = None


def load_settings() -> Settings:
    """Load settings from environment variables and .env file."""
    global settings
    s = Settings()
    s.storage_dir.mkdir(parents=True, exist_ok=True)
    settings = s
    return s


def get_settings() -> Settings:
    """Get the global settings instance, loading if necessary."""
    global settings
    if settings is None:
        settings = load_settings()
    return settings
