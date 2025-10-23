#!/usr/bin/env python3
"""
Boann Security Risk Agent - Public Server
Public-facing server application providing query capabilities for security documents.
This service exposes only the query endpoint to external users.
"""

import os
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from llama_stack_client import LlamaStackClient
import httpx

from src.api.public_api import get_public_router
from src.shared.logging_config import setup_logging, get_logger


# Load environment variables
load_dotenv()


# Setup logging first
setup_logging()
logger = get_logger(__name__)

# Global clients (future: add OpenAI, Gemini, etc.)
llama_client = None
openai_client = None
gemini_client = None

# test
# test2


async def initialize_vector_database(client: LlamaStackClient):
    """Initialize and register the vector database with PGVector"""
    try:
        logger.info("🔧 Initializing vector database...")

        # Get vector DB configuration from environment
        vector_db_id = os.getenv("VECTOR_DB_ID", "boann-vector-db-id")
        rag_provider = os.getenv("VECTOR_DB_PROVIDER", "pgvector").lower()

        # List available providers
        providers = client.providers.list()

        # Find the appropriate vector provider
        vector_provider = None
        if rag_provider == "faiss":
            vector_provider = next(
                (
                    p
                    for p in providers
                    if p.api == "vector_io"
                    and ("faiss" in getattr(p, "provider_id", "").lower())
                ),
                None,
            )
            if vector_provider is None:
                raise RuntimeError("FAISS provider not found in available providers.")
        else:
            # Default to PGVector provider
            vector_provider = next(
                (
                    p
                    for p in providers
                    if p.api == "vector_io"
                    and ("pgvector" in getattr(p, "provider_id", "").lower())
                ),
                None,
            )
            if vector_provider is None:
                raise RuntimeError(
                    "PGVector provider not found in available providers."
                )

        logger.info(f"Found vector provider: {vector_provider.provider_id}")

        # List available embedding models
        models = client.models.list()

        if os.getenv("EMBEDDING_MODEL"):
            embedding_model = os.getenv("EMBEDDING_MODEL")
        else:
            embedding_models = [m for m in models if m.model_type == "embedding"]
            if not embedding_models:
                raise RuntimeError("No embedding models found in available models.")
            # Select the first available embedding model
            embedding_model = embedding_models[0].identifier

        logger.info(f"Using embedding model: {embedding_model}")

        # Check if vector database is already registered
        try:
            existing_dbs = client.vector_dbs.list()
            if any(db.identifier == vector_db_id for db in existing_dbs):
                logger.info(f"✅ Vector database '{vector_db_id}' already registered")
                return
        except Exception as e:
            logger.debug(f"Could not check existing vector databases: {e}")

        # Register the vector database
        client.vector_dbs.register(
            vector_db_id=vector_db_id,
            embedding_model=embedding_model,
            embedding_dimension=int(os.getenv("EMBEDDING_DIMENSION", "384")),
            provider_id=vector_provider.provider_id,
        )

        logger.info(f"✅ Vector database '{vector_db_id}' registered successfully")

    except Exception as e:
        logger.error(f"❌ Failed to initialize vector database: {e}")
        # Don't exit - the API can still work without RAG if ENABLE_RAG=false
        logger.warning(
            "⚠️  Vector database initialization failed, but server will continue running"
        )
        logger.warning("⚠️  RAG functionality will be disabled")


@asynccontextmanager
async def public_lifespan(app: FastAPI):
    logger.info("Starting Boann Security Risk Agent Public Server...")
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
            logger.error("Exiting public server due to LlamaStack connection failure")
            os._exit(1)  # Clean exit without traceback

        # Initialize Llama Stack client with configuration
        # Set longer timeout and retry configuration to handle slow/busy LlamaStack
        logger.info(f"🔧 Initializing LlamaStackClient with base_url: {base_url}")
        logger.info("🔧 Setting timeout to 120 seconds and max_retries to 3")

        app.state.llama_client = LlamaStackClient(
            base_url=base_url,
            timeout=300.0,  # 5 minutes instead of default 1 minute
            max_retries=3,  # Reduce retries to fail faster
        )

        # Test client functionality
        try:
            # Try to list models to verify client works
            models = app.state.llama_client.models.list()
            logger.info(
                f"LlamaStack client initialized successfully. Found {len(models)} models."
            )
        except Exception as client_error:
            logger.error(f"Client functionality test failed: {client_error}")
            logger.error("Exiting public server due to LlamaStack client failure")
            os._exit(1)  # Clean exit without traceback

        # Initialize vector database
        await initialize_vector_database(app.state.llama_client)

    except Exception as e:
        logger.error(f"Critical error during public server startup: {e}")
        logger.error("Exiting public server due to startup failure")
        os._exit(1)  # Clean exit without traceback

    yield
    logger.info("Shutting down Boann Security Risk Agent Public Server...")


app = FastAPI(
    title="Boann Security Risk Agent - Public API",
    description="Public-facing RAG system for security document queries (query-only access)",
    version="1.0.0",
    lifespan=public_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # XXX: in prod, restrict to only the domain that will be used
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(get_public_router())

if __name__ == "__main__":
    uvicorn.run(
        "boann_server:app",
        host=os.getenv("BOANN_HOST", "0.0.0.0"),
        port=int(os.getenv("BOANN_PORT", "8000")),
        reload=os.getenv("RELOAD", "false").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "INFO").lower(),
    )
