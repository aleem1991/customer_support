# src/utils/config.py
# Author: Suresh D R | AI Product Developer & Technology Mentor
#
# Single source of truth for all configuration. Reads from environment
# variables only -- never hardcode credentials anywhere else in the codebase.

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenAI / Azure OpenAI
    OPENAI_API_KEY: str
    AZURE_OPENAI_ENDPOINT: str = "https://enzi-resource.services.ai.azure.com/"
    OPENAI_API_VERSION: str = "2024-06-01"
    OPENAI_DEPLOYMENT_NAME: str = "gpt-4o"

    # AWS
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str = "eu-north-1"
    S3_BUCKET: str = "support-agent-bucket-2026"
    CHROMA_S3_KEY: str = "chroma-db/chroma_db.zip"
    CHROMA_COLLECTION: str = "knowledge_base"
    CHROMA_LOCAL_PATH: str = "/tmp/chroma_db"

    # RDS PostgreSQL
    RDS_HOST: str
    RDS_PORT: str = "5432"
    RDS_DB: str = "supportagent"
    RDS_USER: str
    RDS_PASSWORD: str

    # Redis (ElastiCache or local)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    CACHE_ENABLED: bool = True

    # SageMaker (optional -- falls back to deterministic mock if unset)
    CHURN_ENDPOINT_NAME: str = ""

    # App
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.RDS_USER}:{self.RDS_PASSWORD}"
            f"@{self.RDS_HOST}:{self.RDS_PORT}/{self.RDS_DB}"
        )

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
