#!/usr/bin/env python3
"""Local API server management CLI.

This replaces tools/local_api.sh with a Python-based solution that can be
used both as a standalone CLI tool and imported by tests.

Usage:
    python -m tools.local_api setup    # Fetch secrets and prepare environment
    python -m tools.local_api run      # Start the local API server
    python -m tools.local_api          # Show help
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.svg2ooxml.api.testing import LocalAPIConfig, LocalAPIServer, setup_local_environment

logging.basicConfig(
    level=logging.INFO,
    format="[local-api] %(message)s",
)


def cmd_setup(args: argparse.Namespace) -> int:
    """Set up local environment by fetching secrets."""
    try:
        config = LocalAPIConfig(
            port=int(os.environ.get("SVG2OOXML_LOCAL_PORT", "8080"))
        )
        env_vars = setup_local_environment(config)

        print(f"✓ Setup complete. Fetched {len(env_vars)} environment variables.")
        print(f"✓ Secrets saved to {config.secret_dir}")
        print(f"\nTo start the server, run: {sys.argv[0]} run")

        return 0
    except Exception as exc:
        logging.error(f"Setup failed: {exc}")
        return 1


def cmd_run(args: argparse.Namespace) -> int:
    """Start the local API server."""
    try:
        port = int(os.environ.get("SVG2OOXML_LOCAL_PORT", "8080"))
        config = LocalAPIConfig(port=port)

        # Check if secrets exist
        if not config.secret_dir.exists() or not config.service_account_path.exists():
            logging.error(f"Secrets not found in {config.secret_dir}")
            logging.error(f"Run '{sys.argv[0]} setup' first")
            return 1

        server = LocalAPIServer(config)

        # Ensure environment is set up (will use cached secrets)
        server.setup()

        logging.info(f"Starting server on http://127.0.0.1:{port}")
        logging.info("Press Ctrl+C to stop")

        # Start server (this blocks until interrupted)
        server.start()

        try:
            # Wait for interrupt
            server.process.wait()
        except KeyboardInterrupt:
            logging.info("\nShutting down...")
            server.stop()

        return 0
    except Exception as exc:
        logging.error(f"Server failed: {exc}")
        return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Local API server management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s setup    Fetch secrets from GCP and save to secrets/local/
  %(prog)s run      Start the local API server (requires setup first)

Environment variables:
  SVG2OOXML_LOCAL_PORT    Override default port (default: 8080)
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Setup command
    setup_parser = subparsers.add_parser(
        "setup",
        help="Fetch secrets from Secret Manager and prepare environment",
    )
    setup_parser.set_defaults(func=cmd_setup)

    # Run command
    run_parser = subparsers.add_parser(
        "run",
        help="Start the local API server",
    )
    run_parser.set_defaults(func=cmd_run)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
