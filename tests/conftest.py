"""
Pytest configuration and common fixtures for the test suite
"""

import pytest
import tempfile
import os


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def sample_pdf_file(temp_dir):
    """Create a sample PDF file for testing"""
    pdf_path = os.path.join(temp_dir, "test.pdf")
    # Create a minimal PDF file for testing
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n")
    return pdf_path


@pytest.fixture
def sample_sarif_file(temp_dir):
    """Create a sample SARIF file for testing"""
    sarif_path = os.path.join(temp_dir, "test.sarif")
    sarif_data = {
        "runs": [
            {
                "tool": {"driver": {"name": "TestTool", "version": "1.0.0"}},
                "results": [
                    {
                        "ruleId": "TEST001",
                        "level": "error",
                        "message": {"text": "Test vulnerability found"},
                    }
                ],
            }
        ]
    }

    import json

    with open(sarif_path, "w") as f:
        json.dump(sarif_data, f)
    return sarif_path


@pytest.fixture
def sample_vex_file(temp_dir):
    """Create a sample VEX file for testing"""
    vex_path = os.path.join(temp_dir, "test.vex")
    vex_data = {
        "version": "1.0.0",
        "vulnerabilities": [
            {
                "id": "CVE-2023-1234",
                "status": "affected",
                "description": "Test vulnerability description",
            }
        ],
    }

    import json

    with open(vex_path, "w") as f:
        json.dump(vex_data, f)
    return vex_path


@pytest.fixture
def sample_json_file(temp_dir):
    """Create a sample JSON file for testing"""
    json_path = os.path.join(temp_dir, "test.json")
    json_data = {"name": "Test Data", "value": 123, "nested": {"key": "value"}}

    import json

    with open(json_path, "w") as f:
        json.dump(json_data, f)
    return json_path


@pytest.fixture
def sample_text_file(temp_dir):
    """Create a sample text file for testing"""
    text_path = os.path.join(temp_dir, "test.txt")
    with open(text_path, "w") as f:
        f.write("This is a test text file.\nIt contains multiple lines.\n")
    return text_path


@pytest.fixture
def mock_llamastack_client():
    """Mock LlamaStack client for testing"""
    from unittest.mock import Mock

    mock_client = Mock()

    # Mock providers
    mock_provider = Mock()
    mock_provider.api = "vector_io"
    mock_provider.provider_id = "pgvector"
    mock_client.providers.list.return_value = [mock_provider]

    # Mock models
    mock_model = Mock()
    mock_model.model_type = "embedding"
    mock_model.identifier = "test-embedding-model"
    mock_client.models.list.return_value = [mock_model]

    # Mock vector database
    mock_vector_db = Mock()
    mock_client.vector_dbs.register.return_value = mock_vector_db

    return mock_client


@pytest.fixture
def test_environment():
    """Set up test environment variables"""
    original_env = os.environ.copy()

    # Set test environment variables
    os.environ.update(
        {
            "VECTOR_DB_ID": "test-vector-db-id",
            "CHUNK_SIZE": "500",
            "CHUNK_OVERLAP": "100",
            "SUPPORTED_FORMATS": "pdf,sarif,vex,json,txt",
        }
    )

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)
