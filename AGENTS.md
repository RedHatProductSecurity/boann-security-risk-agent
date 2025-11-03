# AGENTS.md

Guidelines for AI assistants (Claude, Cursor, GitHub Copilot, etc.) when working on this project.

## Project Overview

Boann Security Risk Agent enables OCSF aware question answering and aggregate security risk report draft generation. It is a single pane of glass platform to aggregate various types of security findings into a central place and provide actionable insights and aggregate security risk report drafts.

**Related Project:** [boann-ocsf-security-data-platform](https://github.com/RedHatProductSecurity/boann-ocsf-security-data-platform/)

**Key Components:**
- Dual-service security architecture: Public Service (queries) and Internal Service (admin document ingestion)
- FastAPI-based API for RAG queries (standard and streaming)
- Built on LlamaStack with pluggable LLM providers (Gemini, OpenAI, Ollama, VLLM)
- Vector search support: Faiss (in-memory) or PostgreSQL with pgvector (persistent)
- Document ingestion system supporting PDF, JSON, and text files
- Security-first design with separate API keys and network isolation

**Tech Stack:**
- Python 3.12+ with uv for dependency management
- LlamaStack for LLM orchestration
- FastAPI for REST APIs
- Vector databases: Faiss or pgvector
- Testing: pytest with fixtures, mocking, and async support

**Important Security Notes:**
- The project implements a dual-service architecture for security
- Public Service (port 8000): Query-only access for external users
- Internal Service (port 8001): Admin-only document ingestion (internal access only)
- Never expose the internal service or LlamaStack server to public networks
- Use strong, unique API keys for both services (`BOANN_API_KEY` and `BOANN_ADMIN_API_KEY`)

## Development Setup

See [README.md](README.md) for complete setup instructions, including:
- Environment variable configuration (see `env.example`)
- LlamaStack and Boann server setup
- Container-based deployment options

**Quick Start:**
```bash
# 1. Copy and configure environment variables
cp env.example .env
# Edit .env with your API keys and configuration

# 2. Start both LlamaStack and Boann servers
uv run --env-file .env scripts/start_boann.py
```

**Development Tools:**
- Uses uv for dependency management
- Pre-commit hooks with ruff for linting and formatting
- Install pre-commit hooks: `pre-commit install`

For detailed contribution guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Testing Guidelines

**Test Structure:**
- Tests located in `tests/` directory
- Uses pytest with fixtures and parametrized tests
- Test coverage includes: admin API, public API, and document ingestion
- Async test support with pytest-asyncio

**Test Dependencies:**
- pytest (core testing framework)
- pytest-cov (coverage reporting)
- pytest-mock (mocking support)
- pytest-asyncio (async test support)

**Testing Best Practices:**
- Use fixtures for common setup (see `tests/conftest.py`)
- Mock external dependencies (LlamaStack, LLM providers, vector databases)
- Test both success and error scenarios
- Ensure proper authentication testing for both services
- Test RAG functionality with different vector database backends

## Running Tests

See [README.md](README.md) for test execution instructions.

**Run all tests:**
```bash
uv run pytest
```

**Run with coverage:**
```bash
uv run pytest --cov=src --cov-report=html
```

**Run specific test file:**
```bash
uv run pytest tests/test_admin_api.py
uv run pytest tests/test_public_api.py
uv run pytest tests/test_ingest_documents.py
```

**Run tests in verbose mode:**
```bash
uv run pytest -v
```

Before committing, ensure all tests pass and pre-commit hooks succeed:
```bash
pre-commit run --all-files -v
```

