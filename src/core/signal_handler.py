"""Graceful shutdown handling for Ctrl-C and other signals."""

import signal
import sys


class GracefulShutdown:
    """Handle graceful shutdown on SIGINT and SIGTERM."""

    shutdown_requested = False

    @classmethod
    def setup(cls) -> None:
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, cls._signal_handler)
        signal.signal(signal.SIGTERM, cls._signal_handler)

    @classmethod
    def _signal_handler(cls, signum: int, frame) -> None:
        """Handle shutdown signals.

        Args:
            signum: Signal number
            frame: Current stack frame
        """
        if cls.shutdown_requested:
            # Second signal, force exit
            print("\nForcing shutdown...")
            sys.exit(1)

        cls.shutdown_requested = True
        print("\nShutdown requested. Finishing current operation...")
        print("Press Ctrl-C again to force exit.")

    @classmethod
    def should_shutdown(cls) -> bool:
        """Check if shutdown has been requested.

        Returns:
            True if shutdown requested, False otherwise
        """
        return cls.shutdown_requested

    @classmethod
    def reset(cls) -> None:
        """Reset shutdown flag (useful for testing)."""
        cls.shutdown_requested = False
