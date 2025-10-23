#!/usr/bin/env python3
"""
Start Servers Script
Starts LlamaStack server and waits for it to be ready before starting Boann server.
"""

import os
import sys
import time
import signal
import subprocess
import logging
import asyncio
import httpx
from pathlib import Path
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ServerManager:
    def __init__(self):
        self.llamastack_process: Optional[subprocess.Popen] = None
        self.boann_process: Optional[subprocess.Popen] = None
        self.shutdown_requested = False

        # Get configuration from environment
        self.llamastack_config = os.getenv(
            "LLAMA_STACK_CONFIG_PATH", "examples/config/run-starter-remote-minimal.yaml"
        ).strip()
        self.llamastack_host = os.getenv("LLAMA_STACK_HOST", "localhost")
        self.llamastack_port = os.getenv("LLAMA_STACK_PORT", "8321")
        self.boann_host = os.getenv("BOANN_HOST", "localhost")
        self.boann_port = os.getenv("BOANN_PORT", "8000")

        # Timeout settings
        self.llamastack_startup_timeout = int(
            os.getenv("LLAMASTACK_STARTUP_TIMEOUT", "60")
        )
        self.health_check_timeout = int(os.getenv("HEALTH_CHECK_TIMEOUT", "10"))
        self.health_check_interval = int(os.getenv("HEALTH_CHECK_INTERVAL", "2"))

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.shutdown_requested = True
        self.shutdown()

    def check_environment_variables(self) -> bool:
        """Check if required environment variables are set."""
        vector_db_provider = os.getenv("VECTOR_DB_PROVIDER", "").lower()

        # Only check PGVECTOR_* variables if provider is pgvector
        if vector_db_provider == "pgvector":
            required_vars = [
                "PGVECTOR_HOST",
                "PGVECTOR_PORT",
                "PGVECTOR_DB",
                "PGVECTOR_USER",
                "PGVECTOR_PASSWORD",
            ]

            missing_vars = []
            for var in required_vars:
                if not os.getenv(var):
                    missing_vars.append(var)

            if missing_vars:
                logger.error(
                    f"Missing required environment variables: {', '.join(missing_vars)}"
                )
                logger.error(
                    "Please set these environment variables before running the container."
                )
                logger.error("You can use --env-file .env or set them individually.")
                return False

            logger.info("✅ All required pgvector environment variables are set")
        else:
            logger.info(
                f"✅ Using vector DB provider: {vector_db_provider or 'default'} (skipping pgvector env checks)"
            )

        return True

    def check_llamastack_config(self) -> bool:
        """Check if LlamaStack config file exists."""
        config_path = Path(self.llamastack_config)
        if not config_path.exists():
            logger.error(f"LlamaStack config file {self.llamastack_config} not found!")
            return False
        logger.info(f"Using LlamaStack config: {self.llamastack_config}")
        return True

    async def wait_for_llamastack_health(self) -> bool:
        """Wait for LlamaStack server to be healthy."""
        health_url = f"http://{self.llamastack_host}:{self.llamastack_port}/v1/health"
        start_time = time.time()

        logger.info(f"Waiting for LlamaStack server at {health_url}...")

        while time.time() - start_time < self.llamastack_startup_timeout:
            if self.shutdown_requested:
                return False

            try:
                async with httpx.AsyncClient(
                    timeout=self.health_check_timeout
                ) as client:
                    response = await client.get(health_url)
                    if response.status_code == 200:
                        logger.info("✅ LlamaStack server is healthy and ready!")
                        return True
                    else:
                        logger.warning(
                            f"Health check returned status {response.status_code}"
                        )
            except httpx.ConnectError:
                logger.debug("LlamaStack server not ready yet...")
            except Exception as e:
                logger.debug(f"Health check error: {e}")

            await asyncio.sleep(self.health_check_interval)

        logger.error(
            f"❌ LlamaStack server failed to start within {self.llamastack_startup_timeout} seconds"
        )
        return False

    def start_llamastack_server(self) -> bool:
        """Start the LlamaStack server."""
        try:
            logger.info("🚀 Starting LlamaStack server...")

            # Build the command
            cmd = [
                "python3",
                "-m",
                "llama_stack.cli.llama",
                "stack",
                "run",
                self.llamastack_config,
            ]

            # Start the process
            self.llamastack_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            logger.info(
                f"LlamaStack server started with PID: {self.llamastack_process.pid}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to start LlamaStack server: {e}")
            return False

    def start_boann_server(self) -> bool:
        """Start the Boann server."""
        try:
            logger.info("🚀 Starting Boann server...")

            # Build the command
            cmd = [
                "python3",
                "-m",
                "uvicorn",
                "src.boann_server:app",
                "--host",
                self.boann_host,
                "--port",
                self.boann_port,
            ]

            # Start the process WITHOUT capturing stdout/stderr to prevent buffer deadlock
            # The Boann server has its own logging, so we don't need to capture its output
            self.boann_process = subprocess.Popen(
                cmd, text=True, bufsize=1, universal_newlines=True
            )

            logger.info(f"Boann server started with PID: {self.boann_process.pid}")
            logger.info(
                f"Boann server will be available at: http://{self.boann_host}:{self.boann_port}"
            )
            logger.info(
                "Boann server output will be displayed directly in the terminal"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to start Boann server: {e}")
            return False

    async def monitor_processes(self):
        """Monitor both processes and handle output."""
        tasks = []

        if self.llamastack_process:
            tasks.append(
                self._monitor_process_output(self.llamastack_process, "LlamaStack")
            )

        # Skip monitoring Boann process output since we're not capturing it
        # This prevents the stdout buffer deadlock issue with streaming responses
        # if self.boann_process:
        #     tasks.append(self._monitor_process_output(self.boann_process, "Boann"))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _monitor_process_output(self, process: subprocess.Popen, name: str):
        """Monitor process output and log it."""
        try:
            while process.poll() is None and not self.shutdown_requested:
                line = process.stdout.readline()
                if line:
                    logger.info(f"[{name}] {line.rstrip()}")
                await asyncio.sleep(0.1)

            # Read any remaining output
            remaining_output, _ = process.communicate()
            if remaining_output:
                for line in remaining_output.splitlines():
                    if line.strip():
                        logger.info(f"[{name}] {line}")

        except Exception as e:
            logger.error(f"Error monitoring {name} process: {e}")

    def shutdown(self):
        """Shutdown all processes gracefully."""
        logger.info("🛑 Shutting down servers...")

        if self.boann_process:
            logger.info("Terminating Boann server...")
            self.boann_process.terminate()
            try:
                self.boann_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("Boann server didn't terminate gracefully, forcing...")
                self.boann_process.kill()

        if self.llamastack_process:
            logger.info("Terminating LlamaStack server...")
            self.llamastack_process.terminate()
            try:
                self.llamastack_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "LlamaStack server didn't terminate gracefully, forcing..."
                )
                self.llamastack_process.kill()

        logger.info("✅ All servers shut down")


async def main():
    """Main function to orchestrate server startup."""
    manager = ServerManager()

    try:
        # Check prerequisites
        if not manager.check_environment_variables():
            sys.exit(1)

        if not manager.check_llamastack_config():
            sys.exit(1)

        # Start LlamaStack server
        if not manager.start_llamastack_server():
            sys.exit(1)

        # Wait for LlamaStack to be ready
        if not await manager.wait_for_llamastack_health():
            logger.error("❌ LlamaStack server failed to become healthy")
            manager.shutdown()
            sys.exit(1)

        # Start Boann server
        if not manager.start_boann_server():
            logger.error("❌ Failed to start Boann server")
            manager.shutdown()
            sys.exit(1)

        logger.info("🎉 Both servers are running!")
        logger.info(
            f"📊 LlamaStack: http://{manager.llamastack_host}:{manager.llamastack_port}"
        )
        logger.info(f"🔍 Boann: http://{manager.boann_host}:{manager.boann_port}")
        logger.info("Press Ctrl+C to stop all servers")

        # Monitor processes
        await manager.monitor_processes()

    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
