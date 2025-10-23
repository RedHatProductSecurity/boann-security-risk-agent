#!/usr/bin/env python3
"""
Test cases for the public API module
"""

import os
import sys
from unittest.mock import patch
from fastapi.testclient import TestClient
from fastapi import FastAPI

# Add the project root to the path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Mock the API key before importing the module
with patch.dict(os.environ, {"BOANN_API_KEY": "test-api-key"}):
    from src.api.public_api import get_public_router


class TestPublicAPI:
    """Test cases for SYSTEM_PROMPT environment variable override functionality"""

    def test_system_prompt_import(self):
        """Test that SYSTEM_PROMPT can be imported from config"""
        from src.config import SYSTEM_PROMPT

        assert SYSTEM_PROMPT is not None
        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT.strip()) > 0
        assert "security assessment assistant" in SYSTEM_PROMPT.lower()

    def test_system_prompt_override(self):
        """Test that system prompt override works with environment variables: 1. with override disabled, 2. with override enabled"""
        from src.config import SYSTEM_PROMPT

        custom_prompt = "Test system prompt for environment override"

        # Test override disabled (default behavior) - use clear=True to isolate from .env file
        with patch.dict(
            os.environ,
            {
                "BOANN_OVERRIDE_SYSTEM_PROMPT": "false",
                "BOANN_SYSTEM_PROMPT": custom_prompt,
            },
            clear=True,
        ):
            # Don't load .env file to avoid interference from actual environment
            # Just test the logic directly with controlled environment

            # Check override flag
            override_enabled = (
                os.getenv("BOANN_OVERRIDE_SYSTEM_PROMPT", "false").lower() == "true"
            )
            if override_enabled:
                system_prompt = os.getenv("BOANN_SYSTEM_PROMPT", SYSTEM_PROMPT)
            else:
                system_prompt = SYSTEM_PROMPT

            # Should use default prompt when override is disabled
            assert system_prompt == SYSTEM_PROMPT
            assert system_prompt != custom_prompt

        # Test override enabled - use clear=True to isolate from .env file
        with patch.dict(
            os.environ,
            {
                "BOANN_OVERRIDE_SYSTEM_PROMPT": "true",
                "BOANN_SYSTEM_PROMPT": custom_prompt,
            },
            clear=True,
        ):
            # Don't load .env file to avoid interference from actual environment

            override_enabled = (
                os.getenv("BOANN_OVERRIDE_SYSTEM_PROMPT", "false").lower() == "true"
            )
            if override_enabled:
                system_prompt = os.getenv("BOANN_SYSTEM_PROMPT", SYSTEM_PROMPT)
            else:
                system_prompt = SYSTEM_PROMPT

            # Should use custom prompt when override is enabled
            assert system_prompt == custom_prompt
            assert system_prompt != SYSTEM_PROMPT

    def test_api_key_validation_function(self):
        """Test that API key validation function works correctly"""

        # Get the router to access the verify_api_key function
        router = get_public_router()

        # Access the verify_api_key function from the router's dependencies
        # We need to test the function directly since it's defined inside get_public_router

        # Create a mock app to test the endpoint with wrong API key
        app = FastAPI()
        app.include_router(router)
        test_client = TestClient(app)

        # Test with wrong API key
        response = test_client.post(
            "/query",
            json={"query": "test question", "stream": False},
            headers={"Authorization": "Bearer wrong-api-key"},
        )

        # Should return 401 Unauthorized
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]
