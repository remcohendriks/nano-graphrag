"""FastAPI application for nano-graphrag."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import logging
import redis.asyncio as redis

from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig, StorageConfig
import dataclasses
from .config import settings
from .routers import documents, query, health, management, jobs
from .exceptions import StorageUnavailableError

# Configure nano-graphrag logger with app-managed pattern
# This ensures INFO logs are visible regardless of uvicorn's logging config
import sys
import os

nano_logger = logging.getLogger("nano-graphrag")
nano_logger.setLevel(logging.INFO)

# App-managed pattern: attach our own handler and don't propagate
# This makes us independent of uvicorn's root logger configuration
nano_logger.propagate = False

# Clear any existing handlers to avoid duplicates
nano_logger.handlers.clear()

# Add a console handler that writes to stdout with explicit flush
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)

# Use a clear format that shows the logger name
formatter = logging.Formatter(
    '%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
console_handler.setFormatter(formatter)
nano_logger.addHandler(console_handler)

# Optional: Allow disabling app-managed logging via env var for production
if os.getenv("DISABLE_APP_LOGGING", "false").lower() == "true":
    nano_logger.handlers.clear()
    nano_logger.propagate = True  # Fall back to server-managed pattern

# Get logger for this module
# Note: Logging configuration should be handled by the application server (uvicorn, gunicorn, etc.)
# or via external configuration (logging.ini, environment variables)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage GraphRAG lifecycle."""
    logger.info("Initializing GraphRAG...")

    # Start with complete GraphRAG config from environment
    config = GraphRAGConfig.from_env()

    # Preserve environment config (hybrid_search, node2vec, etc.) and override API settings
    storage_overrides = {
        "working_dir": settings.working_dir,
        "graph_backend": settings.graph_backend,
        "vector_backend": settings.vector_backend,
        "kv_backend": settings.kv_backend,
    }

    if settings.neo4j_url:
        storage_overrides["neo4j_url"] = settings.neo4j_url
        storage_overrides["neo4j_username"] = settings.neo4j_username
        storage_overrides["neo4j_password"] = settings.neo4j_password
        storage_overrides["neo4j_database"] = settings.neo4j_database

    if settings.qdrant_url:
        storage_overrides["qdrant_url"] = settings.qdrant_url
        storage_overrides["qdrant_api_key"] = settings.qdrant_api_key

    if settings.redis_url:
        storage_overrides["redis_url"] = settings.redis_url
        storage_overrides["redis_password"] = settings.redis_password

    storage_config = dataclasses.replace(config.storage, **storage_overrides)

    # Replace only storage config, keeping LLM/embedding/query from env
    config = dataclasses.replace(config, storage=storage_config)

    # Initialize GraphRAG
    try:
        app.state.graphrag = GraphRAG(config=config)
        logger.info("GraphRAG initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize GraphRAG: {e}")
        raise

    # Initialize Redis client for job tracking if Redis URL is configured
    if settings.redis_url:
        try:
            app.state.redis_client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            await app.state.redis_client.ping()
            logger.info("Redis client initialized for job tracking")
        except Exception as e:
            logger.warning(f"Failed to initialize Redis client: {e}")
            app.state.redis_client = None
    else:
        app.state.redis_client = None
        logger.info("Redis not configured - job tracking disabled")

    yield

    # Cleanup
    logger.info("Shutting down GraphRAG...")
    if hasattr(app.state, "redis_client") and app.state.redis_client:
        await app.state.redis_client.close()


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount static files
    app.mount(
        f"{settings.api_prefix}/static",
        StaticFiles(directory="nano_graphrag/api/static"),
        name="static"
    )

    # Include routers (order matters - specific routes first)
    app.include_router(jobs.router, prefix=settings.api_prefix)
    app.include_router(documents.router, prefix=settings.api_prefix)
    app.include_router(query.router, prefix=settings.api_prefix)
    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(management.router, prefix=settings.api_prefix)

    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "name": settings.api_title,
            "version": settings.api_version,
            "docs": f"{settings.api_prefix}/docs"
        }

    return app


# Create default app instance
app = create_app()