"""Tests for FastAPI REST API."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI

from nano_graphrag.api.app import create_app
from nano_graphrag.api.models import QueryMode


@pytest.fixture
def mock_graphrag():
    """Create mock GraphRAG instance."""
    mock = MagicMock()
    mock.ainsert = AsyncMock(return_value=None)
    mock.aquery = AsyncMock(return_value="Test response")

    # Mock storage backends
    mock.full_docs = MagicMock()
    mock.full_docs.get_by_id = AsyncMock(return_value={"content": "Test document"})
    mock.full_docs.delete_by_id = AsyncMock(return_value=True)
    mock.full_docs.drop = AsyncMock(return_value=None)

    mock.text_chunks = MagicMock()
    mock.community_reports = MagicMock()
    mock.llm_response_cache = MagicMock()
    mock.llm_response_cache.drop = AsyncMock(return_value=None)

    mock.chunk_entity_relation_graph = MagicMock()
    mock.entities_vdb = MagicMock()

    return mock


@pytest.fixture
def test_app(mock_graphrag):
    """Create test FastAPI app with mocked GraphRAG."""
    app = FastAPI()

    # Import routers after creating app
    from nano_graphrag.api.routers import documents, query, health, management
    from nano_graphrag.api.config import settings

    # Set GraphRAG in app state
    app.state.graphrag = mock_graphrag

    # Include routers
    app.include_router(documents.router, prefix="/api/v1")
    app.include_router(query.router, prefix="/api/v1")
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(management.router, prefix="/api/v1")

    return app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


def test_document_insert(client: TestClient, mock_graphrag):
    """Test document insertion endpoint."""
    response = client.post(
        "/api/v1/documents",
        json={"content": "Test document content"}
    )

    assert response.status_code == 201
    data = response.json()
    assert "doc_id" in data
    assert data["message"] == "Document processed successfully"


def test_batch_insert(client: TestClient, mock_graphrag):
    """Test batch document insertion."""
    response = client.post(
        "/api/v1/documents/batch",
        json={
            "documents": [
                {"content": "Document 1"},
                {"content": "Document 2"},
                {"content": "Document 3"}
            ]
        }
    )

    assert response.status_code == 201
    data = response.json()
    assert len(data) == 3
    mock_graphrag.ainsert.assert_called_once()


def test_query_local(client: TestClient, mock_graphrag):
    """Test local query mode."""
    response = client.post(
        "/api/v1/query",
        json={
            "question": "What is the meaning of life?",
            "mode": "local"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Test response"
    assert data["mode"] == "local"
    assert "latency_ms" in data
    mock_graphrag.aquery.assert_called_once()


def test_query_global(client: TestClient, mock_graphrag):
    """Test global query mode."""
    response = client.post(
        "/api/v1/query",
        json={
            "question": "What are the main themes?",
            "mode": "global"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "global"


def test_query_naive(client: TestClient, mock_graphrag):
    """Test naive query mode."""
    response = client.post(
        "/api/v1/query",
        json={
            "question": "Simple question",
            "mode": "naive"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "naive"


def test_get_document(client: TestClient, mock_graphrag):
    """Test document retrieval."""
    response = client.get("/api/v1/documents/test_id")

    assert response.status_code == 200
    data = response.json()
    assert data["doc_id"] == "test_id"
    assert "content" in data


def test_delete_document(client: TestClient, mock_graphrag):
    """Test document deletion."""
    response = client.delete("/api/v1/documents/test_id")

    assert response.status_code == 200
    data = response.json()
    assert "deleted" in data["message"]


def test_health_check(client: TestClient):
    """Test health check endpoint."""
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "neo4j" in data
    assert "qdrant" in data
    assert "redis" in data


def test_readiness_probe(client: TestClient):
    """Test readiness probe."""
    response = client.get("/api/v1/health/ready")

    # Backends aren't mocked with health checks, so we expect 503
    if response.status_code == 503:
        assert "detail" in response.json()
    else:
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"


def test_liveness_probe(client: TestClient):
    """Test liveness probe."""
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"


def test_get_info(client: TestClient):
    """Test system information endpoint."""
    response = client.get("/api/v1/info")

    assert response.status_code == 200
    data = response.json()
    assert "nano_graphrag_version" in data
    assert "backends" in data
    assert "llm" in data


def test_get_stats(client: TestClient):
    """Test statistics endpoint."""
    response = client.get("/api/v1/stats")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_clear_cache(client: TestClient, mock_graphrag):
    """Test cache clearing."""
    response = client.post("/api/v1/cache/clear")

    assert response.status_code == 200
    data = response.json()
    assert "message" in data


def test_query_modes(client: TestClient):
    """Test query modes listing."""
    response = client.get("/api/v1/query/modes")

    assert response.status_code == 200
    data = response.json()
    assert "modes" in data
    assert len(data["modes"]) == 3
    mode_names = [m["name"] for m in data["modes"]]
    assert "local" in mode_names
    assert "global" in mode_names
    assert "naive" in mode_names


def test_concurrent_queries(client: TestClient, mock_graphrag):
    """Test handling of concurrent queries."""
    from concurrent.futures import ThreadPoolExecutor

    def make_request(i):
        return client.post("/api/v1/query", json={"question": f"Query {i}", "mode": "local"})

    with ThreadPoolExecutor(max_workers=10) as executor:
        responses = list(executor.map(make_request, range(10)))

    assert all(r.status_code == 200 for r in responses)
    assert mock_graphrag.aquery.call_count == 10