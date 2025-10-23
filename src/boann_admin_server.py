#!/usr/bin/env python3
"""
Security Assessment RAG System - Admin Server (Internal Only)
Internal server application providing document ingestion capabilities for administrators.
This service should only be accessible from within the internal network.
"""

import os
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from llama_stack_client import LlamaStackClient
import httpx

from src.api.admin_api import get_admin_router
from src.shared.logging_config import setup_logging, get_logger

# Load environment variables
load_dotenv()

# Setup logging first
setup_logging()
logger = get_logger(__name__)


async def initialize_vector_database(client: LlamaStackClient):
    """Initialize and register the vector database with PGVector"""

    # Check if RAG is enabled
    if os.getenv("ENABLE_RAG", "false").lower() != "true":
        logger.warning("RAG is disabled - vector database initialization skipped")
        return

    try:
        vector_db_id = os.getenv("VECTOR_DB_ID", "boann-vector-db-id")
        vector_db_provider = os.getenv("VECTOR_DB_PROVIDER", "pgvector")

        # Check if vector database is already registered
        try:
            existing_dbs = client.vector_dbs.list()
            if any(db.identifier == vector_db_id for db in existing_dbs):
                logger.info(f"Vector database '{vector_db_id}' already registered")
                return
        except Exception as list_error:
            logger.warning(f"Could not list existing vector databases: {list_error}")

        # Register the vector database
        if vector_db_provider.lower() == "pgvector":
            # PGVector configuration
            vector_db_config = {
                "identifier": vector_db_id,
                "provider_id": "pgvector",
                "embedding_dimension": int(os.getenv("EMBEDDING_DIMENSION", "768")),
                "provider_config": {
                    "host": os.getenv("PGVECTOR_HOST", "localhost"),
                    "port": int(os.getenv("PGVECTOR_PORT", "5432")),
                    "db": os.getenv("PGVECTOR_DB", "boann"),
                    "user": os.getenv("PGVECTOR_USER", "postgres"),
                    "password": os.getenv("PGVECTOR_PASSWORD", ""),
                },
            }
        else:
            # FAISS configuration (fallback)
            vector_db_config = {
                "vector_db_id": vector_db_id,
                "provider_id": "faiss",
                "embedding_model": os.getenv(
                    "EMBEDDING_MODEL", "gemini/text-embedding-004"
                ),
                "embedding_dimension": int(os.getenv("EMBEDDING_DIMENSION", "768")),
            }

        client.vector_dbs.register(**vector_db_config)
        logger.info(f"Successfully registered vector database: {vector_db_id}")

    except Exception as e:
        logger.error(f"Failed to initialize vector database: {e}")
        logger.warning("⚠️  Document ingestion functionality will be limited")


@asynccontextmanager
async def admin_lifespan(app: FastAPI):
    logger.info("Starting Security Assessment RAG Admin Server...")
    try:
        # Get base URL from environment
        base_url = (
            "http://"
            + os.getenv("LLAMA_STACK_HOST", "localhost")
            + ":"
            + os.getenv("LLAMA_STACK_PORT", "8321")
        )

        # Test connection first
        logger.info(f"Testing connection to LlamaStack at {base_url}")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{base_url}/v1/health")
                if response.status_code == 200:
                    logger.info("LlamaStack connection test successful")
                else:
                    raise Exception(
                        f"Health check returned status {response.status_code}"
                    )
        except Exception as conn_error:
            logger.error(f"Connection test failed: {conn_error}")
            logger.error("Exiting admin server due to LlamaStack connection failure")
            os._exit(1)  # Clean exit without traceback

        # Initialize Llama Stack client with configuration
        app.state.llama_client = LlamaStackClient(base_url=base_url)

        # Test client functionality
        try:
            # Try to list models to verify client works
            models = app.state.llama_client.models.list()
            logger.info(
                f"LlamaStack client initialized successfully. Found {len(models)} models."
            )
        except Exception as client_error:
            logger.error(f"Client functionality test failed: {client_error}")
            logger.error("Exiting admin server due to LlamaStack client failure")
            os._exit(1)  # Clean exit without traceback

        # Initialize vector database
        await initialize_vector_database(app.state.llama_client)

    except Exception as e:
        logger.error(f"Admin server startup failed: {e}")
        os._exit(1)

    yield

    logger.info("Shutting down Security Assessment RAG Admin Server...")


# Create admin FastAPI app
admin_app = FastAPI(
    title="Security Assessment RAG Admin System",
    description="Internal admin system for document ingestion - not accessible from public internet",
    version="1.0.0",
    lifespan=admin_lifespan,
)

# Configure CORS for internal network only
admin_app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:*",
        "http://127.0.0.1:*",
        "https://*.internal.*",
        "https://*.local",
        # Add your internal domain patterns here
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Include admin router
admin_app.include_router(get_admin_router())

if __name__ == "__main__":
    # Get admin server configuration
    admin_host = os.getenv("BOANN_ADMIN_HOST", "0.0.0.0")
    admin_port = int(os.getenv("BOANN_ADMIN_PORT", "8001"))

    logger.info(f"Starting admin server on {admin_host}:{admin_port}")
    logger.warning(
        "🔒 This is an INTERNAL-ONLY admin service - should not be exposed to public internet"
    )

    uvicorn.run(
        "src.boann_admin_server:admin_app",
        host=admin_host,
        port=admin_port,
        reload=False,
        log_level=os.getenv("LOG_LEVEL", "INFO").lower(),
    )
