"""Configuration for FastAPI application."""

from pydantic_settings import BaseSettings
from pydantic import validator, Field
from typing import List, Optional, Union
import json


class Settings(BaseSettings):
    # API Configuration
    api_prefix: str = "/api/v1"
    api_title: str = "nano-graphrag API"
    api_version: str = "1.0.0"
    allowed_origins: Union[str, List[str]] = ["*"]

    @validator('allowed_origins', pre=True)
    def parse_allowed_origins(cls, v):
        """Parse allowed_origins from string or list."""
        if isinstance(v, str):
            # If it's a JSON array string, parse it
            if v.startswith('['):
                try:
                    return json.loads(v)
                except json.JSONDecodeError:
                    return [v]
            # Single origin string
            return [v]
        return v

    # Performance
    max_query_timeout: int = 300  # 5 minutes
    max_concurrent_inserts: int = 10
    max_batch_size: int = Field(default=100, description="Maximum number of documents per batch upload")

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