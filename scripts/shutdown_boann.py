#!/usr/bin/env python3
"""
Shutdown Servers Script
Gracefully shuts down LlamaStack and Boann servers.
Supports selective shutdown with -c/--component option.
"""

import os
import sys
import logging
import psutil
import time
import argparse
from typing import List

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ServerShutdown:
    def __init__(self):
        # Get configuration from environment (same as start script)
        self.llamastack_host = os.getenv("LLAMA_STACK_HOST", "localhost")
        self.llamastack_port = int(os.getenv("LLAMA_STACK_PORT", "8321"))
        self.boann_host = os.getenv("BOANN_HOST", "localhost")
        self.boann_port = int(os.getenv("BOANN_PORT", "8000"))

        # Timeout settings
        self.graceful_timeout = int(os.getenv("SHUTDOWN_GRACEFUL_TIMEOUT", "10"))
        self.force_timeout = int(os.getenv("SHUTDOWN_FORCE_TIMEOUT", "5"))

    def find_processes_by_port(self, port: int) -> List[psutil.Process]:
        """Find processes listening on a specific port."""
        processes = []
        try:
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    # Check if process has network connections
                    connections = proc.net_connections(kind="inet")
                    for conn in connections:
                        if (
                            conn.laddr.port == port
                            and conn.status == psutil.CONN_LISTEN
                        ):
                            processes.append(proc)
                            break
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    pass
        except Exception as e:
            logger.debug(f"Error finding processes on port {port}: {e}")

        return processes

    def find_processes_by_name(self, patterns: List[str]) -> List[psutil.Process]:
        """Find processes by command line patterns."""
        processes = []
        try:
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    cmdline = " ".join(proc.cmdline()) if proc.cmdline() else ""
                    for pattern in patterns:
                        if pattern in cmdline:
                            processes.append(proc)
                            break
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    pass
        except Exception as e:
            logger.debug(f"Error finding processes by patterns {patterns}: {e}")

        return processes

    def find_llamastack_processes(self) -> List[psutil.Process]:
        """Find LlamaStack server processes."""
        processes = []

        # Try to find by port first
        port_processes = self.find_processes_by_port(self.llamastack_port)
        processes.extend(port_processes)

        # Try to find by command line patterns
        patterns = [
            "llama_stack.cli.llama",
            "llama stack run",
            f":{self.llamastack_port}",
        ]
        name_processes = self.find_processes_by_name(patterns)

        # Add unique processes
        for proc in name_processes:
            if proc not in processes:
                processes.append(proc)

        return processes

    def find_boann_processes(self) -> List[psutil.Process]:
        """Find Boann server processes."""
        processes = []

        # Try to find by port first
        port_processes = self.find_processes_by_port(self.boann_port)
        processes.extend(port_processes)

        # Try to find by command line patterns
        patterns = ["src.boann_server:app", "boann_server", f":{self.boann_port}"]
        name_processes = self.find_processes_by_name(patterns)

        # Add unique processes
        for proc in name_processes:
            if proc not in processes:
                processes.append(proc)

        return processes

    def terminate_process_gracefully(self, process: psutil.Process, name: str) -> bool:
        """Terminate a process gracefully with timeout."""
        try:
            logger.info(f"Terminating {name} process (PID: {process.pid})...")

            # Send SIGTERM for graceful shutdown
            process.terminate()

            # Wait for graceful shutdown
            try:
                process.wait(timeout=self.graceful_timeout)
                logger.info(f"✅ {name} process terminated gracefully")
                return True
            except psutil.TimeoutExpired:
                logger.warning(
                    f"⏰ {name} process didn't terminate gracefully within {self.graceful_timeout}s"
                )

                # Force kill
                logger.info(f"🔨 Force killing {name} process...")
                process.kill()

                try:
                    process.wait(timeout=self.force_timeout)
                    logger.info(f"✅ {name} process force killed")
                    return True
                except psutil.TimeoutExpired:
                    logger.error(
                        f"❌ Failed to kill {name} process (PID: {process.pid})"
                    )
                    return False

        except psutil.NoSuchProcess:
            logger.info(f"✅ {name} process already terminated")
            return True
        except Exception as e:
            logger.error(f"❌ Error terminating {name} process: {e}")
            return False

    def shutdown_processes(self, processes: List[psutil.Process], name: str) -> bool:
        """Shutdown a list of processes."""
        if not processes:
            logger.info(f"No {name} processes found")
            return True

        logger.info(f"Found {len(processes)} {name} process(es)")

        all_success = True
        for process in processes:
            try:
                cmdline = " ".join(process.cmdline()) if process.cmdline() else "N/A"
                logger.info(f"{name} process: PID {process.pid}, CMD: {cmdline}")

                success = self.terminate_process_gracefully(process, f"{name}")
                if not success:
                    all_success = False

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                logger.info(f"✅ {name} process already terminated or inaccessible")

        return all_success

    def check_ports_free(self) -> bool:
        """Check if the ports are now free."""
        ports_to_check = [self.llamastack_port, self.boann_port]

        for port in ports_to_check:
            processes = self.find_processes_by_port(port)
            if processes:
                logger.warning(f"⚠️  Port {port} is still in use")
                return False

        logger.info("✅ All ports are now free")
        return True

    def shutdown_all(self) -> bool:
        """Shutdown all Boann and LlamaStack processes."""
        logger.info("🛑 Starting shutdown process for all servers...")

        success = True

        # Shutdown Boann server first (dependent on LlamaStack)
        logger.info("=" * 50)
        logger.info("Shutting down Boann server...")
        boann_processes = self.find_boann_processes()
        if not self.shutdown_processes(boann_processes, "Boann"):
            success = False

        # Wait a moment for graceful shutdown
        time.sleep(1)

        # Shutdown LlamaStack server
        logger.info("=" * 50)
        logger.info("Shutting down LlamaStack server...")
        llamastack_processes = self.find_llamastack_processes()
        if not self.shutdown_processes(llamastack_processes, "LlamaStack"):
            success = False

        # Wait and check if ports are free
        time.sleep(2)
        logger.info("=" * 50)
        logger.info("Checking port status...")
        self.check_ports_free()

        if success:
            logger.info("🎉 All servers shut down successfully!")
        else:
            logger.warning("⚠️  Some processes may not have shut down cleanly")

        return success

    def shutdown_boann_only(self) -> bool:
        """Shutdown only Boann server processes."""
        logger.info("🛑 Starting shutdown process for Boann server only...")

        logger.info("=" * 50)
        logger.info("Shutting down Boann server...")
        boann_processes = self.find_boann_processes()
        success = self.shutdown_processes(boann_processes, "Boann")

        # Wait and check if Boann port is free
        time.sleep(1)
        logger.info("=" * 50)
        logger.info("Checking Boann port status...")
        processes = self.find_processes_by_port(self.boann_port)
        if not processes:
            logger.info(f"✅ Port {self.boann_port} (Boann) is now free")
        else:
            logger.warning(f"⚠️  Port {self.boann_port} (Boann) is still in use")
            success = False

        if success:
            logger.info("🎉 Boann server shut down successfully!")
        else:
            logger.warning("⚠️  Boann server may not have shut down cleanly")

        return success

    def shutdown_llamastack_only(self) -> bool:
        """Shutdown only LlamaStack server processes."""
        logger.info("🛑 Starting shutdown process for LlamaStack server only...")

        logger.info("=" * 50)
        logger.info("Shutting down LlamaStack server...")
        llamastack_processes = self.find_llamastack_processes()
        success = self.shutdown_processes(llamastack_processes, "LlamaStack")

        # Wait and check if LlamaStack port is free
        time.sleep(1)
        logger.info("=" * 50)
        logger.info("Checking LlamaStack port status...")
        processes = self.find_processes_by_port(self.llamastack_port)
        if not processes:
            logger.info(f"✅ Port {self.llamastack_port} (LlamaStack) is now free")
        else:
            logger.warning(
                f"⚠️  Port {self.llamastack_port} (LlamaStack) is still in use"
            )
            success = False

        if success:
            logger.info("🎉 LlamaStack server shut down successfully!")
        else:
            logger.warning("⚠️  LlamaStack server may not have shut down cleanly")

        return success


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Gracefully shutdown Boann and LlamaStack servers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Shutdown both servers
  %(prog)s -c boann          # Shutdown only Boann server
  %(prog)s -c llamastack     # Shutdown only LlamaStack server
  %(prog)s --component all   # Shutdown both servers (explicit)
        """,
    )

    parser.add_argument(
        "-c",
        "--component",
        choices=["all", "boann", "llamastack"],
        default="all",
        help="Component to shutdown (default: all)",
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    return parser.parse_args()


def main():
    """Main function to orchestrate server shutdown."""
    args = parse_arguments()

    # Configure logging level based on verbose flag
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    shutdown_manager = ServerShutdown()

    try:
        # Determine which shutdown method to call
        if args.component == "all":
            success = shutdown_manager.shutdown_all()
        elif args.component == "boann":
            success = shutdown_manager.shutdown_boann_only()
        elif args.component == "llamastack":
            success = shutdown_manager.shutdown_llamastack_only()
        else:
            logger.error(f"Unknown component: {args.component}")
            sys.exit(1)

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        logger.info("Shutdown interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error during shutdown: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
