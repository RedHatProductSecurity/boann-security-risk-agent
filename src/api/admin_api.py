#!/usr/bin/env python3
"""
Admin API - Ingest endpoints only
This module contains only the document ingestion functionality for internal/admin use.
"""

from fastapi import APIRouter, HTTPException, Depends, status, Request, File, UploadFile
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import List
import os
import tempfile
import shutil
from pathlib import Path

from src.shared.document_processor import DocumentProcessorManager

# Import centralized logging configuration
from src.shared.logging_config import get_logger

logger = get_logger(__name__)

# Security - Admin API key for ingest operations
security = HTTPBearer()
BOANN_ADMIN_API_KEY = os.getenv("BOANN_ADMIN_API_KEY")
if not BOANN_ADMIN_API_KEY:
    raise ValueError("BOANN_ADMIN_API_KEY environment variable must be set")

VECTOR_DB_ID = os.getenv("VECTOR_DB_ID", "boann-vector-db-id")


# Pydantic models
class IngestResponse(BaseModel):
    success: bool = Field(..., description="Whether the ingestion was successful")
    message: str = Field(..., description="Success or error message")
    processed_files: int = Field(
        0, description="Number of files successfully processed"
    )
    failed_files: int = Field(0, description="Number of files that failed to process")
    errors: List[str] = Field(
        default_factory=list, description="List of error messages"
    )


def get_admin_router():
    """Create and return the admin API router with ingest endpoints only"""
    router = APIRouter()

    def verify_admin_api_key(
        credentials: HTTPAuthorizationCredentials = Depends(security),
    ) -> str:
        """Verify admin API key for ingest operations"""
        if credentials.credentials != BOANN_ADMIN_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid admin API key",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return credentials.credentials

    @router.get("/admin/health")
    async def admin_health():
        """Health check endpoint for admin service"""
        return {"status": "healthy", "service": "admin", "endpoints": ["ingest"]}

    @router.post("/ingest", response_model=IngestResponse)
    async def ingest_documents(
        files: List[UploadFile] = File(..., description="Documents to ingest"),
        request: Request = None,
        api_key: str = Depends(verify_admin_api_key),
    ):
        """
        Ingest documents into the vector database for RAG.

        Accepts multiple file uploads and processes them for storage in the vector database.
        Supported formats: PDF, JSON, etc (handled as text) files.

        This endpoint is only available on the internal admin service.
        """

        client = getattr(request.app.state, "llama_client", None)
        if not client:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="LlamaStack client not available",
            )

        # Check if RAG is enabled
        if os.getenv("ENABLE_RAG", "false").lower() != "true":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RAG is not enabled. Set ENABLE_RAG=true to use this endpoint.",
            )

        # Initialize document processor
        doc_processor = DocumentProcessorManager()

        # Statistics tracking
        stats = {"processed_files": 0, "failed_files": 0, "errors": []}

        # Process each uploaded file
        for file in files:
            try:
                # Security check: validate file size
                max_size = int(
                    os.getenv("MAX_DOCUMENT_SIZE", "104857600")
                )  # 100MB default
                if file.size and file.size > max_size:
                    error_msg = (
                        f"File {file.filename} exceeds maximum size ({max_size} bytes)"
                    )
                    logger.warning(error_msg)
                    stats["failed_files"] += 1
                    stats["errors"].append(error_msg)
                    continue

                # Create temporary file to process
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=f"_{file.filename}"
                ) as tmp_file:
                    # Copy uploaded file content to temporary file
                    shutil.copyfileobj(file.file, tmp_file)
                    tmp_file_path = tmp_file.name

                try:
                    # Process the document
                    text, metadata_from_doc_processor, success = (
                        doc_processor.process_document(tmp_file_path)
                    )

                    if success and text.strip():
                        # Add to vector database
                        chunk_size = int(os.getenv("CHUNK_SIZE", "1000"))
                        chunks = doc_processor.chunk_text(text, chunk_size)

                        # Prepare all chunks for batch insertion
                        batch_chunks = []
                        for i, chunk in enumerate(chunks):
                            chunk_metadata = {
                                **metadata_from_doc_processor,
                                "chunk_index": i,
                                "total_chunks": len(chunks),
                                "file_name": file.filename,
                                "document_id": metadata_from_doc_processor.get(
                                    "document_id", file.filename
                                ),
                                "chunk_id": f"{metadata_from_doc_processor.get('document_id', file.filename)}_chunk_{i}",
                            }

                            batch_chunks.append(
                                {"content": chunk, "metadata": chunk_metadata}
                            )

                        # Insert all chunks in a single batch request
                        client.vector_io.insert(
                            vector_db_id=VECTOR_DB_ID, chunks=batch_chunks
                        )

                        logger.info(
                            f"Successfully processed {file.filename}: {len(chunks)} chunks"
                        )
                        stats["processed_files"] += 1
                    else:
                        error_msg = f"Failed to extract text from {file.filename}"
                        logger.warning(error_msg)
                        stats["failed_files"] += 1
                        stats["errors"].append(error_msg)

                except Exception as proc_error:
                    error_msg = (
                        f"Processing error for {file.filename}: {str(proc_error)}"
                    )
                    logger.error(error_msg)
                    stats["failed_files"] += 1
                    stats["errors"].append(error_msg)

                finally:
                    # Clean up temporary file
                    try:
                        Path(tmp_file_path).unlink()
                    except Exception as cleanup_error:
                        logger.warning(
                            f"Failed to cleanup temp file {tmp_file_path}: {cleanup_error}"
                        )

            except Exception as file_error:
                error_msg = (
                    f"File handling error for {file.filename}: {str(file_error)}"
                )
                logger.error(error_msg)
                stats["failed_files"] += 1
                stats["errors"].append(error_msg)

        # Generate response
        total_files = len(files)
        success = stats["processed_files"] > 0

        if stats["processed_files"] == total_files:
            message = f"Successfully ingested {stats['processed_files']} documents"
        elif stats["processed_files"] > 0:
            message = f"Partially successful: {stats['processed_files']}/{total_files} documents ingested"
        else:
            message = (
                f"Failed to ingest any documents. {stats['failed_files']} files failed"
            )

        logger.info(f"Ingestion complete: {message}")

        return IngestResponse(
            success=success,
            message=message,
            processed_files=stats["processed_files"],
            failed_files=stats["failed_files"],
            errors=stats["errors"],
        )

    return router
