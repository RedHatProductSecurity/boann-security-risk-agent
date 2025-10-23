#!/usr/bin/env python3
"""
Test cases for the admin API module
"""

import os
import sys
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

# Add the project root to the path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Mock the admin API key before importing the module
with patch.dict(os.environ, {"BOANN_ADMIN_API_KEY": "test-admin-api-key"}):
    from src.api.admin_api import get_admin_router


class TestAdminAPI:
    """Test cases for admin API functionality"""

    def test_admin_health_endpoint(self):
        """Test that the admin health endpoint returns correct response"""
        router = get_admin_router()
        app = FastAPI()
        app.include_router(router)
        test_client = TestClient(app)

        response = test_client.get("/admin/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "admin"
        assert "ingest" in data["endpoints"]

    def test_admin_api_key_validation(self):
        """Test that admin API key validation works correctly"""
        router = get_admin_router()
        app = FastAPI()
        app.include_router(router)
        test_client = TestClient(app)

        # Test with wrong API key
        response = test_client.post(
            "/ingest",
            files=[("files", ("test.txt", "test content", "text/plain"))],
            headers={"Authorization": "Bearer wrong-admin-api-key"},
        )

        # Should return 401 Unauthorized
        assert response.status_code == 401
        assert "Invalid admin API key" in response.json()["detail"]

    def test_admin_api_key_validation_missing_auth(self):
        """Test that missing authorization header returns 403"""
        router = get_admin_router()
        app = FastAPI()
        app.include_router(router)
        test_client = TestClient(app)

        # Test without authorization header
        response = test_client.post(
            "/ingest",
            files=[("files", ("test.txt", "test content", "text/plain"))],
        )

        # Should return 403 Forbidden (FastAPI returns 403 for missing auth)
        assert response.status_code == 403

    @patch.dict(os.environ, {"ENABLE_RAG": "false"})
    def test_ingest_with_rag_disabled(self):
        """Test that ingest endpoint returns error when RAG is disabled"""
        # Mock the llama client to avoid the 500 error
        mock_llama_client = MagicMock()

        router = get_admin_router()
        app = FastAPI()
        app.state.llama_client = mock_llama_client
        app.include_router(router)
        test_client = TestClient(app)

        response = test_client.post(
            "/ingest",
            files=[("files", ("test.txt", "test content", "text/plain"))],
            headers={"Authorization": "Bearer test-admin-api-key"},
        )

        # Should return 400 Bad Request
        assert response.status_code == 400
        assert "RAG is not enabled" in response.json()["detail"]

    @patch.dict(os.environ, {"ENABLE_RAG": "true"})
    @patch("src.api.admin_api.DocumentProcessorManager")
    def test_ingest_with_rag_enabled_mock_client(self, mock_doc_processor):
        """Test ingest endpoint with RAG enabled and mocked dependencies"""
        # Mock the document processor
        mock_processor_instance = MagicMock()
        mock_processor_instance.process_document.return_value = (
            "test content",
            {"document_id": "test"},
            True,
        )
        mock_processor_instance.chunk_text.return_value = ["chunk1", "chunk2"]
        mock_doc_processor.return_value = mock_processor_instance

        # Mock the llama client
        mock_llama_client = MagicMock()
        mock_vector_io = MagicMock()
        mock_llama_client.vector_io = mock_vector_io

        router = get_admin_router()
        app = FastAPI()
        app.state.llama_client = mock_llama_client
        app.include_router(router)
        test_client = TestClient(app)

        response = test_client.post(
            "/ingest",
            files=[("files", ("test.txt", "test content", "text/plain"))],
            headers={"Authorization": "Bearer test-admin-api-key"},
        )

        # Should return 200 OK
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["processed_files"] == 1
        assert data["failed_files"] == 0

    @patch.dict(os.environ, {"ENABLE_RAG": "true"})
    def test_ingest_missing_llama_client(self):
        """Test that ingest endpoint returns error when llama client is missing"""
        router = get_admin_router()
        app = FastAPI()
        # Don't set llama_client on app.state
        app.include_router(router)
        test_client = TestClient(app)

        response = test_client.post(
            "/ingest",
            files=[("files", ("test.txt", "test content", "text/plain"))],
            headers={"Authorization": "Bearer test-admin-api-key"},
        )

        # Should return 500 Internal Server Error
        assert response.status_code == 500
        assert "LlamaStack client not available" in response.json()["detail"]

    def test_ingest_response_model(self):
        """Test that the IngestResponse model has correct structure"""
        from src.api.admin_api import IngestResponse

        # Test successful response
        response = IngestResponse(
            success=True,
            message="Test message",
            processed_files=1,
            failed_files=0,
            errors=[],
        )

        assert response.success is True
        assert response.message == "Test message"
        assert response.processed_files == 1
        assert response.failed_files == 0
        assert response.errors == []

        # Test failed response
        response = IngestResponse(
            success=False,
            message="Failed message",
            processed_files=0,
            failed_files=1,
            errors=["Test error"],
        )

        assert response.success is False
        assert response.message == "Failed message"
        assert response.processed_files == 0
        assert response.failed_files == 1
        assert response.errors == ["Test error"]
