"""
Centralized logging configuration for Refract interfaces.

This module provides logging configuration helpers for different interfaces
(CLI, API, MCP) with appropriate log levels and filters for third-party libraries.
"""
import logging


class ThirdPartyLogFilter(logging.Filter):
    """Filter to exclude or limit logs from noisy third-party libraries."""

    # List of module prefixes to silence or limit
    NOISY_MODULES = [
        'asyncio',
        'sse_starlette',
        'LiteLLM',
        'litellm',
        'httpcore',
        'httpx',
        'mcp',
        'fastapi_mcp',
    ]

    def filter(self, record):
        """Exclude logs from noisy third-party modules."""
        for noisy in self.NOISY_MODULES:
            if record.name.startswith(noisy):
                return False
        return True


def configure_cli_logging(verbose: bool = False):
    """
    Configure logging for CLI interface.

    Args:
        verbose: If True, use DEBUG level for refract.* modules.
                 If False, use INFO level (cleaner output).

    Sets up:
    - INFO level by default (WARNING for third-party)
    - DEBUG level when verbose=True
    - Filters out noisy third-party libraries
    """
    # Set base level based on verbose flag
    base_level = logging.DEBUG if verbose else logging.INFO

    # Configure root logger with clean format for CLI
    logging.basicConfig(
        level=base_level,
        format='[%(levelname)s] %(message)s',  # Simple format for CLI
        force=True  # Override any existing configuration
    )

    # Add filter to exclude third-party noise
    root_logger = logging.getLogger()
    root_logger.addFilter(ThirdPartyLogFilter())

    # Silence third-party libraries explicitly
    _silence_third_party_loggers()

    # Set refract modules to appropriate level
    refract_level = logging.DEBUG if verbose else logging.INFO
    refract_logger = logging.getLogger('refract')
    refract_logger.setLevel(refract_level)

    # Inform user when verbose mode is active
    if verbose:
        refract_logger.info("Verbose mode enabled (DEBUG level)")


def configure_api_logging():
    """
    Configure logging for API/MCP servers.

    API servers need more detailed logging for debugging,
    so we use DEBUG level but still filter third-party noise.
    """
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True
    )

    # Add filter to exclude third-party noise
    root_logger = logging.getLogger()
    root_logger.addFilter(ThirdPartyLogFilter())

    # Silence third-party libraries
    _silence_third_party_loggers()


def _silence_third_party_loggers():
    """Silence noisy third-party loggers by setting them to WARNING level."""
    noisy_loggers = [
        'asyncio',
        'LiteLLM',
        'litellm',
        'httpcore',
        'httpx',
        'sse_starlette',
        'mcp',
        'fastapi_mcp',
    ]

    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

        # Also silence common sub-loggers
        for sub in ['connection', 'http11', 'sse', 'server', 'lowlevel', 'client']:
            logging.getLogger(f'{logger_name}.{sub}').setLevel(logging.WARNING)

        # Silence nested sub-loggers
        for nested in ['server.lowlevel.server', 'server.sse', 'server.lowlevel']:
            logging.getLogger(f'{logger_name}.{nested}').setLevel(logging.WARNING)
