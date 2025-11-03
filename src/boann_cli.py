#!/usr/bin/env python3
"""
Boann CLI - Command line interface for interacting with Boann LlamaStack Agent API
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional
import httpx
import asyncio


class BoannClient:
    """Client for interacting with Boann API"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        verify_ssl: bool | str = True,
        show_source: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.verify_ssl = verify_ssl
        self.show_source = show_source
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Validate SSL configuration
        if isinstance(verify_ssl, str):
            cert_path = Path(verify_ssl).expanduser().resolve()
            if not cert_path.exists():
                raise ValueError(f"CA certificate file does not exist: {verify_ssl}")
            if not cert_path.is_file():
                raise ValueError(f"CA certificate path is not a file: {verify_ssl}")
            self.verify_ssl = str(cert_path)

    async def query(self, query: str, stream: bool = True) -> None:
        """Send a query to the Boann API"""
        url = f"{self.base_url}/query"
        payload = {"query": query, "stream": stream}

        async with httpx.AsyncClient(timeout=120.0, verify=self.verify_ssl) as client:
            if stream:
                await self._handle_streaming_response(client, url, payload)
            else:
                await self._handle_json_response(client, url, payload)

    async def _handle_streaming_response(
        self, client: httpx.AsyncClient, url: str, payload: dict
    ) -> None:
        """Handle Server-Sent Events streaming response"""
        try:
            async with client.stream(
                "POST", url, headers=self.headers, json=payload
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    print(
                        f"Error {response.status_code}: {error_text.decode()}",
                        file=sys.stderr,
                    )
                    return

                print("Streaming response:")
                print("-" * 50)

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_content = line[6:]  # Remove "data: " prefix

                        if data_content == "[DONE]":
                            print("\n✅ Stream completed")
                            break

                        try:
                            data = json.loads(data_content)

                            if data.get("type") == "token":
                                print(data.get("content", ""), end="", flush=True)
                            elif data.get("type") == "metadata":
                                if self.show_source:
                                    print("\n\nRAG Metadata:")
                                    self._print_metadata(data.get("metadata", {}))
                            elif data.get("type") == "error":
                                print(
                                    f"\n❌ Error: {data.get('content', '')}",
                                    file=sys.stderr,
                                )

                        except json.JSONDecodeError:
                            continue  # Skip malformed JSON

        except httpx.RequestError as e:
            print(f"❌ Network error connecting to {url}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"❌ Unexpected error: {e}", file=sys.stderr)

    async def _handle_json_response(
        self, client: httpx.AsyncClient, url: str, payload: dict
    ) -> None:
        """Handle non-streaming JSON response"""
        try:
            response = await client.post(url, headers=self.headers, json=payload)

            if response.status_code != 200:
                print(f"Error {response.status_code}: {response.text}", file=sys.stderr)
                return

            data = response.json()
            print("Response:")
            print("-" * 50)
            print(data.get("content", "No content received"))

            if self.show_source and "metadata" in data:
                print("\nRAG Metadata:")
                self._print_metadata(data["metadata"])

        except httpx.RequestError as e:
            print(f"❌ Network error connecting to {url}: {e}", file=sys.stderr)
        except json.JSONDecodeError:
            print("❌ Invalid JSON response", file=sys.stderr)
        except Exception as e:
            print(f"❌ Unexpected error: {e}", file=sys.stderr)

    def _print_metadata(self, metadata: dict) -> None:
        """Print RAG metadata in a formatted way"""
        total_chunks = metadata.get("total_chunks", 0)
        print(f"  Total chunks retrieved: {total_chunks}")

        rag_chunks = metadata.get("rag_chunks", [])
        if rag_chunks:
            print("  Chunk details:")
            for chunk in rag_chunks:
                chunk_idx = chunk.get("chunk_index", "N/A")
                score = chunk.get("score", "N/A")
                source = chunk.get("source_file_name", "Unknown")
                print(f"    #{chunk_idx}: {source} (score: {score})")

    async def health_check(self) -> None:
        """Check API health status"""
        url = f"{self.base_url}/health"

        print("health check URL: ", url)
        try:
            async with httpx.AsyncClient(
                timeout=10.0, verify=self.verify_ssl
            ) as client:
                response = await client.get(url)

                if response.status_code == 200:
                    data = response.json()
                    print("✅ API is healthy")
                    print(f"   Service: {data.get('service', 'unknown')}")
                    print(f"   Status: {data.get('status', 'unknown')}")
                    if "endpoints" in data:
                        print(f"   Available endpoints: {', '.join(data['endpoints'])}")
                else:
                    print(
                        f"❌ API health check failed: {response.status_code}",
                        file=sys.stderr,
                    )

        except httpx.RequestError as e:
            print(f"❌ Cannot reach API at {url}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"❌ Health check error: {e}", file=sys.stderr)


def load_config(
    api_key_arg: Optional[str] = None,
    base_url_arg: Optional[str] = None,
    insecure: bool = False,
    cacert: Optional[str] = None,
    parser=None,
):
    """Load configuration from CLI arguments or environment variables"""
    # Priority: CLI argument > environment variable > default
    api_key = api_key_arg or os.getenv("BOANN_API_KEY")
    base_url = base_url_arg or os.getenv("BOANN_API_URL") or "http://localhost:8000"

    if not api_key:
        if parser:
            parser.error(
                "API key must be provided via --api-key argument or BOANN_API_KEY environment variable"
            )
        else:
            print("❌ Error: API key must be provided", file=sys.stderr)
            print(
                "   Use --api-key argument or set BOANN_API_KEY environment variable",
                file=sys.stderr,
            )
            sys.exit(1)

    # SSL verification configuration
    if insecure:
        verify_ssl = False
    elif cacert:
        verify_ssl = cacert
    else:
        verify_ssl = True

    return base_url, api_key, verify_ssl


def cli_main():
    """Console script entry point"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Operation cancelled by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"❌ Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


async def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Boann CLI - Query the Boann LlamaStack Agent API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Authentication:
  You can set either --api-key or BOANN_API_KEY environment variable for authentication.

Examples:
  # Stream a query (default)
  boann query "What are the top three security risks of Product X(your product)?"
  
  # Generate security posture report
  boann report "Product X(your product) 4.15"
  
  # With custom URL
  boann -u "https://your.boann-api.url" query "<query text>"
  
  # Show source documents and relevance scores
  boann query "<query text>" --show-source
  
  # Non-streaming query
  boann query "<query text>" --no-stream
  
  # Non-streaming report with source information
  boann report "Product X(your product) 4.15" --no-stream --show-source
  
  # Check API health
  boann health
  
  # Disable SSL verification (insecure, like curl -k)
  boann -k -u "https://your.boann-api.url" health
  
  # Use custom CA certificate
  boann --cacert "/path/to/ca.pem" -u "https://your.boann-api.url" health
  
Environment Variables:
  BOANN_API_KEY     API key for authentication (fallback if --api-key not provided)
  BOANN_API_URL     Base URL for the API (fallback if -u not provided, default: http://localhost:8000)
        """,
    )

    # Global options
    parser.add_argument(
        "--api-key",
        help="API key for authentication (overrides BOANN_API_KEY environment variable)",
    )
    parser.add_argument(
        "-u",
        "--url",
        help="Base URL for the Boann API service (overrides BOANN_API_URL environment variable)",
    )
    parser.add_argument(
        "-k",
        "--insecure",
        action="store_true",
        help="Disable SSL certificate verification (like curl -k)",
    )
    parser.add_argument(
        "--cacert", help="Path to CA certificate file for SSL verification"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Query command
    query_parser = subparsers.add_parser("query", help="Send a query to the API")
    query_parser.add_argument("text", help="Query text to send")
    query_parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Disable streaming and get complete response at once",
    )
    query_parser.add_argument(
        "--show-source",
        action="store_true",
        help="Show RAG metadata including source documents and relevance scores",
    )

    # Health command
    subparsers.add_parser("health", help="Check API health status")

    # Report command
    report_parser = subparsers.add_parser(
        "report", help="Generate a draft security posture report for a product"
    )
    report_parser.add_argument(
        "product",
        help="Product name and version to generate security posture report for",
    )
    report_parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Disable streaming and get complete response at once",
    )
    report_parser.add_argument(
        "--show-source",
        action="store_true",
        help="Show RAG metadata including source documents and relevance scores",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load configuration
    base_url, api_key, verify_ssl = load_config(
        args.api_key, args.url, args.insecure, args.cacert, parser
    )

    # Get show_source flag if available (not all commands have it)
    show_source = getattr(args, "show_source", False)
    client = BoannClient(base_url, api_key, verify_ssl, show_source)

    # Execute command
    if args.command == "query":
        stream = not args.no_stream
        print(f"Querying: {args.text}")
        if not stream:
            print("Using non-streaming mode")
        print()
        await client.query(args.text, stream=stream)

    elif args.command == "health":
        await client.health_check()

    elif args.command == "report":
        stream = not args.no_stream
        query_text = f"Generate a draft security posture report for {args.product}"
        print(f"Generating security posture report for: {args.product}")
        if not stream:
            print("Using non-streaming mode")
        print()
        await client.query(query_text, stream=stream)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Operation cancelled by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"❌ Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
