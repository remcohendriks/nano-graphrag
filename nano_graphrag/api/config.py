"""Configuration for FastAPI application."""

from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    # API Configuration
    api_prefix: str = "/api/v1"
    api_title: str = "nano-graphrag API"
    api_version: str = "1.0.0"
    allowed_origins: List[str] = ["*"]

    # Performance
    max_query_timeout: int = 300  # 5 minutes
    max_concurrent_inserts: int = 10
    max_batch_size: int = 100

    # Backend URLs
    neo4j_url: Optional[str] = None
    neo4j_username: Optional[str] = None
    neo4j_password: Optional[str] = None
    neo4j_database: str = "neo4j"

    qdrant_url: Optional[str] = None
    qdrant_api_key: Optional[str] = None

    redis_url: Optional[str] = None
    redis_password: Optional[str] = None

    # Storage backends
    graph_backend: str = "networkx"
    vector_backend: str = "nano"
    kv_backend: str = "json"

    # Working directory
    working_dir: str = "./api_working_dir"

    # LLM settings
    llm_provider: str = "openai"
    llm_model: str = "gpt-5-mini"
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra environment variables


settings = Settings()