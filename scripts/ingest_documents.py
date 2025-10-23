#!/usr/bin/env python3
"""
Security Assessment RAG System - Document Ingestion Script
Processes security documents (PDFs, JSON, etc.) via the admin API /ingest endpoint.
Runs once when requested.
"""

import os
import time
import sys
import logging
from pathlib import Path
from typing import Dict, Any
import requests

from dotenv import load_dotenv

try:
    from tqdm import tqdm
except ImportError:
    # Fallback if tqdm is not available
    class tqdm:
        def __init__(self, total=None, desc=None):
            self.total = total
            self.desc = desc
            self.n = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def update(self, n=1):
            self.n += n


# Load environment variables
load_dotenv()

# Configure logging at module level, but will be overridden in main()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Default to INFO level
)

logger = logging.getLogger(__name__)


class DocumentIngestionScript:
    """Document ingestion script that uses the admin API /ingest endpoint"""

    def __init__(self):
        # Configuration
        admin_host = os.getenv("BOANN_ADMIN_HOST", "localhost")
        admin_port = os.getenv("BOANN_ADMIN_PORT", "8001")

        # Ensure we have a proper URL with protocol
        if admin_host.startswith(("http://", "https://")):
            self.admin_api_base_url = f"{admin_host}:{admin_port}"
        else:
            self.admin_api_base_url = f"http://{admin_host}:{admin_port}"

        self.admin_api_key = os.getenv("BOANN_ADMIN_API_KEY")
        self.max_file_size = int(
            os.getenv("MAX_DOCUMENT_SIZE", "104857600")
        )  # 100MB default
        self.supported_formats = os.getenv("SUPPORTED_FORMATS", "pdf,json,txt").split(
            ","
        )

        if not self.admin_api_key:
            raise ValueError("BOANN_ADMIN_API_KEY environment variable must be set")

        logger.info(f"Admin API URL: {self.admin_api_base_url}")
        logger.debug(
            f"Admin API Key configured: {'Yes' if self.admin_api_key else 'No'}"
        )

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

    def _is_supported_format(self, file_path: Path) -> bool:
        """Check if file format is supported"""
        extension = file_path.suffix.lower().lstrip(".")
        return extension in self.supported_formats

    def send_file_to_api(self, file_path: Path) -> Dict[str, Any]:
        """Send a single file to admin API /ingest endpoint"""
        try:
            # Prepare file for upload
            with open(file_path, "rb") as file_handle:
                files = [("files", (file_path.name, file_handle))]

                # Prepare headers with admin API key
                headers = {"Authorization": f"Bearer {self.admin_api_key}"}

                # Make request to admin API
                url = f"{self.admin_api_base_url}/ingest"
                logger.info(f"Sending file '{file_path.name}' to {url}")
                logger.debug(f"Request headers: {headers}")

                response = requests.post(
                    url,
                    files=files,
                    headers=headers,
                    timeout=300,  # 5 minute timeout for large files
                )

            # Check response
            if response.status_code == 200:
                result = response.json()
                logger.info(f"API response for {file_path.name}: {result}")
                return result
            else:
                error_msg = f"API request failed for {file_path.name} with status {response.status_code}: {response.text}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "message": error_msg,
                    "processed_files": 0,
                    "failed_files": 1,
                    "errors": [error_msg],
                }

        except requests.exceptions.RequestException as e:
            error_msg = f"Request failed for {file_path.name}: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg,
                "processed_files": 0,
                "failed_files": 1,
                "errors": [error_msg],
            }
        except Exception as e:
            error_msg = f"Unexpected error for {file_path.name}: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg,
                "processed_files": 0,
                "failed_files": 1,
                "errors": [error_msg],
            }

    def process_directory(self, directory_path: str) -> Dict[str, Any]:
        """Process all documents in directory by sending them to admin API"""
        directory = Path(directory_path)
        if not directory.exists():
            logger.error(f"Directory does not exist: {directory_path}")
            return {
                "success": False,
                "message": "Directory not found",
                "processed_files": 0,
                "failed_files": 0,
                "errors": ["Directory not found"],
            }

        # Find all files recursively
        all_files = list(directory.rglob("*"))
        valid_files = []
        stats = {
            "success": True,
            "total_files": 0,
            "processed_files": 0,
            "failed_files": 0,
            "errors": [],
        }

        # Filter and validate files
        for file_path in all_files:
            if file_path.is_file():
                stats["total_files"] += 1

                # Security validation
                if not self._is_safe_path(file_path):
                    logger.warning(f"Skipping unsafe file path: {file_path}")
                    stats["failed_files"] += 1
                    stats["errors"].append(f"Unsafe file path: {file_path}")
                    continue

                # File size validation
                try:
                    file_size = file_path.stat().st_size
                    if file_size > self.max_file_size:
                        file_size_mb = file_size / (1024 * 1024)
                        max_size_mb = self.max_file_size / (1024 * 1024)
                        logger.warning(
                            f"Skipping large file: {file_path} ({file_size_mb:.1f}MB > {max_size_mb:.1f}MB limit)"
                        )
                        stats["failed_files"] += 1
                        stats["errors"].append(f"File too large: {file_path}")
                        continue
                except Exception as e:
                    logger.warning(f"Could not check file size for {file_path}: {e}")
                    stats["failed_files"] += 1
                    stats["errors"].append(f"File stat error: {file_path}: {str(e)}")
                    continue

                # Format validation
                if not self._is_supported_format(file_path):
                    logger.debug(f"Skipping unsupported format: {file_path}")
                    continue

                valid_files.append(file_path)
                logger.debug(f"Queued for processing: {file_path}")

        if not valid_files:
            logger.warning("No valid files found to process")
            return {
                "success": False,
                "message": "No valid files found to process",
                "processed_files": 0,
                "failed_files": stats["failed_files"],
                "errors": stats["errors"],
            }

        # Send files to API one by one
        total_processed = 0
        total_failed = 0
        all_errors = stats["errors"].copy()

        with tqdm(total=len(valid_files), desc="Processing documents") as pbar:
            for file_path in valid_files:
                logger.info(f"Processing file: {file_path.name}")

                result = self.send_file_to_api(file_path)

                total_processed += result.get("processed_files", 0)
                total_failed += result.get("failed_files", 0)
                all_errors.extend(result.get("errors", []))

                pbar.update(1)
                time.sleep(1)

        # Final statistics
        final_stats = {
            "success": total_processed > 0,
            "total_files": stats["total_files"],
            "processed_files": total_processed,
            "failed_files": total_failed
            + stats["failed_files"],  # Include validation failures
            "errors": all_errors,
        }

        return final_stats

    def run(self, directory_path: str = None):
        """Main script execution"""
        logger.info("Starting Document Ingestion Script via Admin API...")

        try:
            if not directory_path or not os.path.exists(directory_path):
                error_msg = f"Directory not found: {directory_path}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "message": error_msg,
                    "processed_files": 0,
                    "failed_files": 0,
                    "errors": [error_msg],
                }

            stats = self.process_directory(directory_path)
            logger.info(f"Ingestion complete: {stats}")
            return stats

        except Exception as e:
            error_msg = f"Script error: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg,
                "processed_files": 0,
                "failed_files": 0,
                "errors": [error_msg],
            }


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Document Ingestion Script via Admin API"
    )
    parser.add_argument("--directory", "-d", help="Directory to process (required)")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Update logging level based on arguments
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        # When verbose is not set, keep INFO level but filter requests
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)

    if not args.directory:
        print("❌ Error: --directory argument is required")
        print("Example: python scripts/ingest_documents.py -d ./knowledge")
        sys.exit(1)

    try:
        script = DocumentIngestionScript()
        result = script.run(args.directory)

        if result.get("success", False):
            print("✅ Ingestion completed successfully!")
            print(f"   Total files: {result.get('total_files', 0)}")
            print(f"   Processed: {result.get('processed_files', 0)} files")
            print(f"   Failed: {result.get('failed_files', 0)} files")
            if result.get("errors"):
                print(f"   Errors: {len(result['errors'])}")
            sys.exit(0)
        else:
            print(f"❌ Ingestion failed: {result.get('message', 'Unknown error')}")
            if result.get("errors"):
                print("Errors:")
                for error in result["errors"][:5]:  # Show first 5 errors
                    print(f"   - {error}")
                if len(result["errors"]) > 5:
                    print(f"   ... and {len(result['errors']) - 5} more errors")
            sys.exit(1)

    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        print("Please ensure BOANN_ADMIN_API_KEY environment variable is set")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
