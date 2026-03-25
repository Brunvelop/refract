"""
Centralized logging configuration for Refract interfaces.

This module provides logging configuration helpers for different interfaces
(CLI, API, MCP) with appropriate log levels and filters for third-party libraries.

All noisy third-party prefixes are defined once in ``_NOISY_PREFIXES``.
The ``startswith`` check covers sub-loggers automatically
(e.g. ``mcp.server.lowlevel`` is caught by the ``"mcp"`` prefix).
"""
__all__ = ["ThirdPartyLogFilter", "configure_cli_logging", "configure_api_logging"]

import logging

# Third-party libraries that produce noisy logs at DEBUG level.
# Covers the full dependency chain pulled in by fastapi-mcp:
#   fastapi-mcp → mcp SDK → sse-starlette, httpx → httpcore
_NOISY_PREFIXES = ('asyncio', 'sse_starlette', 'httpcore', 'httpx', 'mcp', 'fastapi_mcp')


class ThirdPartyLogFilter(logging.Filter):
    """Filter to exclude logs from noisy third-party libraries.

    Uses ``startswith`` so all sub-loggers are covered automatically
    (e.g. ``mcp.server.lowlevel``, ``httpx._client``, etc.).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Return False (drop) for any record whose logger name matches a noisy prefix."""
        return not any(record.name.startswith(prefix) for prefix in _NOISY_PREFIXES)


def configure_cli_logging(verbose: bool = False) -> None:
    """Configure logging for CLI interface.

    Args:
        verbose: If True, use DEBUG level for refract.* modules.
                 If False, use INFO level (cleaner output).

    Sets up:
    - INFO level by default (DEBUG when verbose=True)
    - Filters out all noisy third-party libraries via ``ThirdPartyLogFilter``
    """
    base_level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=base_level,
        format='[%(levelname)s] %(message)s',
        force=True
    )

    root = logging.getLogger()
    if not any(isinstance(f, ThirdPartyLogFilter) for f in root.filters):
        root.addFilter(ThirdPartyLogFilter())

    refract_logger = logging.getLogger('refract')
    refract_logger.setLevel(base_level)

    if verbose:
        refract_logger.info("Verbose mode enabled (DEBUG level)")


def configure_api_logging() -> None:
    """Configure logging for API/MCP servers.

    Uses DEBUG level for refract modules with clean timestamp format,
    while filtering all noisy third-party libraries.
    """
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True
    )

    root = logging.getLogger()
    if not any(isinstance(f, ThirdPartyLogFilter) for f in root.filters):
        root.addFilter(ThirdPartyLogFilter())
