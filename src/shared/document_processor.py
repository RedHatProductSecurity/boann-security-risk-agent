#!/usr/bin/env python3
"""
Shared Document Processing Components
This module contains document processing functionality shared between services.
"""

import os
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# Document processing imports
try:
    import pypdf
except ImportError:
    pypdf = None

# Import centralized logging configuration
from src.shared.logging_config import get_logger

logger = get_logger(__name__)


class DocumentProcessor:
    """Base class for document processors"""

    def __init__(self):
        self.supported_extensions = []

    def can_process(self, file_path: str) -> bool:
        """Check if this processor can handle the file"""
        return Path(file_path).suffix.lower() in self.supported_extensions

    def extract_text(self, file_path: str) -> str:
        """Extract text from document"""
        raise NotImplementedError

    def extract_metadata(self, file_path: str) -> Dict[str, Any]:
        """Extract metadata from document"""
        raise NotImplementedError


class PDFProcessor(DocumentProcessor):
    """Process PDF documents"""

    def __init__(self):
        super().__init__()
        self.supported_extensions = [".pdf"]
        if not pypdf:
            logger.warning("pypdf not available - PDF processing disabled")
            self.supported_extensions = []

    def extract_text(self, file_path: str) -> str:
        """Extract text from PDF"""
        if not pypdf:
            raise RuntimeError("pypdf not available for PDF processing")

        try:
            text = ""
            with open(file_path, "rb") as file:
                pdf_reader = pypdf.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
            return text.strip()
        except Exception as e:
            logger.error(f"Failed to extract text from PDF {file_path}: {e}")
            return ""

    def extract_metadata(self, file_path: str) -> Dict[str, Any]:
        """Extract metadata from PDF"""
        if not pypdf:
            return self._basic_metadata(file_path)

        try:
            with open(file_path, "rb") as file:
                pdf_reader = pypdf.PdfReader(file)
                metadata = {
                    "file_extension": ".pdf",
                    "processing_method": "pypdf",
                    "processor": "PDFProcessor",
                }

                # Add PDF metadata if available
                if pdf_reader.metadata:
                    pdf_meta = pdf_reader.metadata
                    if pdf_meta.title:
                        metadata["title"] = pdf_meta.title
                    if pdf_meta.author:
                        metadata["author"] = pdf_meta.author
                    if pdf_meta.subject:
                        metadata["subject"] = pdf_meta.subject
                    if pdf_meta.creator:
                        metadata["creator"] = pdf_meta.creator
                    if pdf_meta.producer:
                        metadata["producer"] = pdf_meta.producer
                    if pdf_meta.creation_date:
                        metadata["creation_date"] = str(pdf_meta.creation_date)
                    if pdf_meta.modification_date:
                        metadata["modification_date"] = str(pdf_meta.modification_date)

                # Add page count
                metadata["page_count"] = len(pdf_reader.pages)

                return metadata
        except Exception as e:
            logger.error(f"Failed to extract metadata from PDF {file_path}: {e}")
            return self._basic_metadata(file_path)

    def _basic_metadata(self, file_path: str) -> Dict[str, Any]:
        """Generate basic metadata when PDF processing fails"""
        return {
            "file_extension": ".pdf",
            "processing_method": "basic",
            "processor": "PDFProcessor",
        }


class JSONProcessor(DocumentProcessor):
    """Process JSON documents"""

    def __init__(self):
        super().__init__()
        self.supported_extensions = [".json"]

    def extract_text(self, file_path: str) -> str:
        """Extract text from JSON, handling various structures"""
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)

            # Convert JSON to readable text
            text_parts = []

            def extract_text_recursive(obj, prefix=""):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if isinstance(value, (dict, list)):
                            extract_text_recursive(value, f"{prefix}{key}: ")
                        else:
                            text_parts.append(f"{prefix}{key}: {value}")
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        if isinstance(item, (dict, list)):
                            extract_text_recursive(item, f"{prefix}[{i}] ")
                        else:
                            text_parts.append(f"{prefix}[{i}] {item}")
                else:
                    text_parts.append(f"{prefix}{obj}")

            extract_text_recursive(data)
            return "\n".join(text_parts)

        except Exception as e:
            logger.error(f"Failed to extract text from JSON {file_path}: {e}")
            return ""

    def extract_metadata(self, file_path: str) -> Dict[str, Any]:
        """Extract metadata from JSON"""
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)

            metadata = {
                "file_extension": ".json",
                "processing_method": "json_parser",
                "processor": "JSONProcessor",
            }

            # Extract common JSON metadata fields
            if isinstance(data, dict):
                metadata["json_keys"] = list(data.keys())
                metadata["json_structure"] = "object"

                # Look for common metadata fields
                for field in [
                    "title",
                    "name",
                    "description",
                    "summary",
                    "version",
                    "date",
                    "author",
                ]:
                    if field in data:
                        metadata[field] = data[field]
            elif isinstance(data, list):
                metadata["json_structure"] = "array"
                metadata["json_array_length"] = len(data)

            return metadata

        except Exception as e:
            logger.error(f"Failed to extract metadata from JSON {file_path}: {e}")
            return {}


class DocumentProcessorManager:
    """Manages document processing across different file types"""

    def __init__(self):
        self.processors = [PDFProcessor(), JSONProcessor()]

        # Configuration
        self.chunk_size = int(os.getenv("CHUNK_SIZE", "1000"))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "200"))
        self.max_file_size = int(
            os.getenv("MAX_DOCUMENT_SIZE", "104857600")
        )  # 100MB default

    def get_processor(self, file_path: str) -> Optional[DocumentProcessor]:
        """Get appropriate processor for file"""
        for processor in self.processors:
            if processor.can_process(file_path):
                return processor
        return None

    def _is_safe_path(self, file_path: Path) -> bool:
        """Validate file path is safe"""
        try:
            # Check for path traversal attempts
            if ".." in str(file_path):
                return False
            # Check if file exists and is a file
            if not file_path.exists() or not file_path.is_file():
                return False
            return True
        except (OSError, ValueError):
            return False

    def chunk_text(self, text: str, chunk_size: int = None) -> List[str]:
        """Split text into semantic chunks with improved strategy"""
        if chunk_size is None:
            chunk_size = self.chunk_size

        if not text or not text.strip():
            return []

        # Clean the text
        text = re.sub(r"\s+", " ", text.strip())

        if len(text) <= chunk_size:
            return [text]

        chunks = []
        overlap = self.chunk_overlap

        # Try to split on sentences first
        sentences = re.split(r"(?<=[.!?])\s+", text)

        current_chunk = ""
        for sentence in sentences:
            # If adding this sentence exceeds chunk size, save current chunk
            if len(current_chunk) + len(sentence) > chunk_size and current_chunk:
                chunks.append(current_chunk.strip())

                # Start new chunk with overlap from previous chunk
                if overlap > 0 and len(current_chunk) > overlap:
                    current_chunk = current_chunk[-overlap:] + " " + sentence
                else:
                    current_chunk = sentence
            else:
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence

        # Add the last chunk if there's content
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        # Handle very long sentences that exceed chunk_size
        final_chunks = []
        for chunk in chunks:
            if len(chunk) <= chunk_size:
                final_chunks.append(chunk)
            else:
                # Split long chunks by character count
                words = chunk.split()
                current_sub_chunk = ""
                for word in words:
                    if len(current_sub_chunk) + len(word) + 1 <= chunk_size:
                        if current_sub_chunk:
                            current_sub_chunk += " " + word
                        else:
                            current_sub_chunk = word
                    else:
                        if current_sub_chunk:
                            final_chunks.append(current_sub_chunk)
                        current_sub_chunk = word

                if current_sub_chunk:
                    final_chunks.append(current_sub_chunk)

        return final_chunks

    def process_document(self, file_path: str) -> Tuple[str, Dict[str, Any], bool]:
        """
        Process a single document with security validation

        Returns:
            Tuple of (text, metadata, success)
        """
        file_path = Path(file_path)

        # Security validation
        if not self._is_safe_path(file_path):
            logger.error(f"Unsafe file path: {file_path}")
            return "", {}, False

        # File size validation
        try:
            file_size = file_path.stat().st_size
            if file_size > self.max_file_size:
                logger.error(
                    f"File too large: {file_path} ({file_size / (1024 * 1024):.1f}MB)"
                )
                return "", {}, False

            logger.info(
                f"Processing file: {file_path} ({file_size / (1024 * 1024):.1f}MB)"
            )

            # Get processor
            processor = self.get_processor(str(file_path))
            if processor:
                # Extract text and metadata
                text = processor.extract_text(str(file_path))
                metadata = processor.extract_metadata(str(file_path))
            else:
                logger.warning(
                    f"No processor found for file: {file_path}, using file content as text"
                )
                # Read file content directly and create basic metadata
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        text = f.read()
                        metadata = {
                            "file_extension": file_path.suffix,
                            "processing_method": "direct_file_read",
                            "processor": "none",
                        }
                except Exception as e:
                    logger.error(f"Failed to read file {file_path}: {e}")
                    return "", {}, False

            if not text.strip():
                logger.warning(f"No text extracted from: {file_path}")
                return "", {}, False

            logger.info(
                f"Successfully processed {file_path}: {len(text)} characters extracted"
            )
            return text, metadata, True

        except Exception as e:
            logger.error(f"Error processing document {file_path}: {e}")
            return "", {}, False
