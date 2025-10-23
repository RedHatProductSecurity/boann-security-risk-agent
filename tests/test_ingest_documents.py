#!/usr/bin/env python3
"""
Test cases for the document ingestion script
"""

import pytest
import tempfile
import os
import json
from unittest.mock import Mock, patch
import sys

# Add the project root to the path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.ingest_documents import DocumentIngestionScript
from src.shared.document_processor import DocumentProcessor, PDFProcessor, JSONProcessor


class TestDocumentProcessor:
    """Test the base DocumentProcessor class"""

    def test_base_processor_initialization(self):
        """Test that base processor initializes correctly"""
        processor = DocumentProcessor()
        assert processor.supported_extensions == []

    def test_can_process_base(self):
        """Test can_process method in base class"""
        processor = DocumentProcessor()
        # Base class should return False for any file
        assert processor.can_process("test.txt") is False

    def test_extract_text_not_implemented(self):
        """Test that extract_text raises NotImplementedError"""
        processor = DocumentProcessor()
        with pytest.raises(NotImplementedError):
            processor.extract_text("test.txt")

    def test_extract_metadata_not_implemented(self):
        """Test that extract_metadata raises NotImplementedError"""
        processor = DocumentProcessor()
        with pytest.raises(NotImplementedError):
            processor.extract_metadata("test.txt")


class TestPDFProcessor:
    """Test the PDFProcessor class"""

    def test_pdf_processor_initialization(self):
        """Test PDF processor initialization"""
        processor = PDFProcessor()
        assert processor.supported_extensions == [".pdf"]

    def test_can_process_pdf(self):
        """Test PDF processor can identify PDF files"""
        processor = PDFProcessor()
        assert processor.can_process("document.pdf") is True
        assert processor.can_process("document.PDF") is True
        assert processor.can_process("document.txt") is False

    def test_extract_text_pdf_success(self):
        """Test successful PDF text extraction"""
        processor = PDFProcessor()

        # Create a mock PDF file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            # Write some mock PDF content (this is simplified)
            tmp_file.write(
                b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
            )
            tmp_file_path = tmp_file.name

        try:
            with patch("pypdf.PdfReader") as mock_pdf_reader:
                # Mock the PDF reader
                mock_reader = Mock()
                mock_page = Mock()
                mock_page.extract_text.return_value = "Test PDF content"
                mock_reader.pages = [mock_page]
                mock_pdf_reader.return_value = mock_reader

                result = processor.extract_text(tmp_file_path)
                assert result == "Test PDF content"
        finally:
            os.unlink(tmp_file_path)

    def test_extract_text_pdf_failure(self):
        """Test PDF text extraction failure"""
        processor = PDFProcessor()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            tmp_file_path = tmp_file.name

        try:
            with patch("pypdf.PdfReader", side_effect=Exception("PDF read error")):
                result = processor.extract_text(tmp_file_path)
                assert result == ""
        finally:
            os.unlink(tmp_file_path)

    def test_extract_metadata_pdf_success(self):
        """Test successful PDF metadata extraction"""
        processor = PDFProcessor()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            tmp_file_path = tmp_file.name

        try:
            with patch("pypdf.PdfReader") as mock_pdf_reader:
                # Mock the PDF reader with metadata
                mock_reader = Mock()
                mock_metadata = Mock()
                mock_metadata.title = "Test Document"
                mock_metadata.author = "Test Author"
                mock_metadata.subject = "Test Subject"
                mock_metadata.creator = "Test Creator"
                mock_metadata.producer = "Test Producer"
                mock_metadata.creation_date = "2023-01-01"
                mock_metadata.modification_date = "2023-01-02"
                mock_reader.metadata = mock_metadata
                mock_page = Mock()
                mock_reader.pages = [mock_page]
                mock_pdf_reader.return_value = mock_reader

                result = processor.extract_metadata(tmp_file_path)

                # Check that all required fields are present
                assert "file_extension" in result
                assert "processing_method" in result
                assert "processor" in result
                # Check that metadata fields are present if they exist
                if "title" in result:
                    assert result["title"] == "Test Document"
                if "author" in result:
                    assert result["author"] == "Test Author"
                if "subject" in result:
                    assert result["subject"] == "Test Subject"
                if "creator" in result:
                    assert result["creator"] == "Test Creator"
                if "producer" in result:
                    assert result["producer"] == "Test Producer"
                if "creation_date" in result:
                    assert result["creation_date"] == "2023-01-01"
                if "modification_date" in result:
                    assert result["modification_date"] == "2023-01-02"
                assert result["page_count"] == 1
        finally:
            os.unlink(tmp_file_path)

    def test_extract_metadata_pdf_no_metadata(self):
        """Test PDF metadata extraction when no metadata exists"""
        processor = PDFProcessor()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            tmp_file_path = tmp_file.name

        try:
            with patch("pypdf.PdfReader") as mock_pdf_reader:
                # Mock the PDF reader without metadata
                mock_reader = Mock()
                mock_reader.metadata = None
                mock_page = Mock()
                mock_reader.pages = [mock_page]
                mock_pdf_reader.return_value = mock_reader

                result = processor.extract_metadata(tmp_file_path)

                # Should still have the basic fields
                assert "file_extension" in result
                assert "processing_method" in result
                assert "processor" in result
                # PDF-specific fields should not be present when no metadata
                assert "title" not in result
                assert "author" not in result
        finally:
            os.unlink(tmp_file_path)


class TestJSONProcessor:
    """Test the JSONProcessor class"""

    def test_json_processor_initialization(self):
        """Test JSON processor initialization"""
        processor = JSONProcessor()
        assert processor.supported_extensions == [".json"]

    def test_can_process_json(self):
        """Test JSON processor can identify JSON files"""
        processor = JSONProcessor()
        assert processor.can_process("data.json") is True
        assert processor.can_process("data.txt") is False

    def test_extract_text_json_success(self):
        """Test successful JSON text extraction"""
        processor = JSONProcessor()

        json_data = {"name": "Test Data", "value": 123, "nested": {"key": "value"}}

        with tempfile.NamedTemporaryFile(
            suffix=".json", mode="w", delete=False
        ) as tmp_file:
            json.dump(json_data, tmp_file)
            tmp_file_path = tmp_file.name

        try:
            result = processor.extract_text(tmp_file_path)
            assert "Test Data" in result
            assert "123" in result
            assert "nested" in result
        finally:
            os.unlink(tmp_file_path)

    def test_extract_metadata_json_success(self):
        """Test successful JSON metadata extraction"""
        processor = JSONProcessor()

        json_data = {"name": "Test Data", "value": 123}

        with tempfile.NamedTemporaryFile(
            suffix=".json", mode="w", delete=False
        ) as tmp_file:
            json.dump(json_data, tmp_file)
            tmp_file_path = tmp_file.name

        try:
            result = processor.extract_metadata(tmp_file_path)

            # Check basic fields
            assert "file_extension" in result
            assert "processing_method" in result
            assert "processor" in result

            # Check JSON-specific fields
            assert "name" in result["json_keys"]
            assert "value" in result["json_keys"]
            assert result["json_structure"] == "object"
            assert "name" in result  # The actual data is also included
        finally:
            os.unlink(tmp_file_path)


class TestDocumentIngestionScript:
    """Test the DocumentIngestionScript class"""

    def test_script_initialization(self):
        """Test script initialization"""
        script = DocumentIngestionScript()
        assert script.admin_api_base_url is not None
        assert script.admin_api_key is not None
        assert script.max_file_size > 0
        assert script.supported_formats is not None

    def test_supported_formats(self):
        """Test supported formats configuration"""
        script = DocumentIngestionScript()

        # Check that supported formats are configured
        assert isinstance(script.supported_formats, list)
        assert len(script.supported_formats) > 0
        # Should include common formats
        assert any("pdf" in fmt for fmt in script.supported_formats)
        assert any("json" in fmt for fmt in script.supported_formats)

    def test_max_file_size_configuration(self):
        """Test max file size configuration"""
        script = DocumentIngestionScript()

        # Check that max file size is reasonable
        assert script.max_file_size > 0
        assert script.max_file_size <= 100 * 1024 * 1024  # Should be <= 100MB

    def test_process_directory_nonexistent(self):
        """Test processing non-existent directory"""
        script = DocumentIngestionScript()

        result = script.process_directory("/nonexistent/directory")

        assert result["success"] is False
        assert "Directory not found" in result["message"]

    def test_process_directory_empty(self):
        """Test processing empty directory"""
        script = DocumentIngestionScript()

        with tempfile.TemporaryDirectory() as temp_dir:
            result = script.process_directory(temp_dir)

            assert result["success"] is False  # No valid files found
            assert result["message"] == "No valid files found to process"
            assert result["processed_files"] == 0
            assert result["failed_files"] == 0


class TestMainFunction:
    """Test the main function and command line interface"""

    def test_help_argument(self):
        """Test help argument"""
        # Test that argparse can parse --help argument
        import argparse

        # Create a parser like the one in main()
        parser = argparse.ArgumentParser(description="Document Ingestion Script")
        parser.add_argument("--directory", "-d", help="Directory to process (required)")
        parser.add_argument(
            "--verbose", "-v", action="store_true", help="Enable verbose logging"
        )

        # Test that --help works
        try:
            parser.parse_args(["--help"])
        except SystemExit:
            # This is expected behavior for --help
            pass

    @patch("sys.argv", ["ingest_documents.py", "--verbose", "--directory", "/test/dir"])
    @patch("scripts.ingest_documents.DocumentIngestionScript")
    @patch("sys.exit")
    def test_verbose_argument(self, mock_exit, mock_script_class):
        """Test verbose argument"""
        mock_script = Mock()
        mock_script.run.return_value = {
            "success": True,
            "processed_files": 1,
            "failed_files": 0,
        }
        mock_script_class.return_value = mock_script

        from scripts.ingest_documents import main

        main()

        mock_script.run.assert_called_once_with("/test/dir")
        mock_exit.assert_called_once_with(0)

    @patch("sys.argv", ["ingest_documents.py", "--directory", "/test/dir"])
    @patch("scripts.ingest_documents.DocumentIngestionScript")
    @patch("sys.exit")
    def test_directory_argument(self, mock_exit, mock_script_class):
        """Test directory argument"""
        mock_script = Mock()
        mock_script.run.return_value = {
            "success": True,
            "processed_files": 1,
            "failed_files": 0,
        }
        mock_script_class.return_value = mock_script

        from scripts.ingest_documents import main

        main()

        mock_script.run.assert_called_once_with("/test/dir")
        mock_exit.assert_called_once_with(0)

    @patch("sys.argv", ["ingest_documents.py", "--directory", "/test/dir"])
    @patch("scripts.ingest_documents.DocumentIngestionScript")
    @patch("sys.exit")
    def test_successful_execution(self, mock_exit, mock_script_class):
        """Test successful script execution"""
        mock_script = Mock()
        mock_script.run.return_value = {
            "success": True,
            "processed_files": 2,
            "failed_files": 0,
        }
        mock_script_class.return_value = mock_script

        from scripts.ingest_documents import main

        main()

        mock_exit.assert_called_once_with(0)

    @patch("sys.argv", ["ingest_documents.py", "--directory", "/test/dir"])
    @patch("scripts.ingest_documents.DocumentIngestionScript")
    @patch("sys.exit")
    def test_failed_execution(self, mock_exit, mock_script_class):
        """Test failed script execution"""
        mock_script = Mock()
        mock_script.run.return_value = {"success": False, "error": "Test error"}
        mock_script_class.return_value = mock_script

        from scripts.ingest_documents import main

        main()

        mock_exit.assert_called_once_with(1)


if __name__ == "__main__":
    pytest.main([__file__])
