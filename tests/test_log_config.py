"""
Tests for refract.log_config module.

Covers ThirdPartyLogFilter, configure_cli_logging, and configure_api_logging.
"""
import logging
import pytest

from refract.log_config import (
    ThirdPartyLogFilter,
    configure_cli_logging,
    configure_api_logging,
    _NOISY_PREFIXES,
)


def _make_record(name: str) -> logging.LogRecord:
    """Helper: create a minimal LogRecord with the given logger name."""
    return logging.LogRecord(
        name=name,
        level=logging.DEBUG,
        pathname="",
        lineno=0,
        msg="test message",
        args=(),
        exc_info=None,
    )


# ============================================================================
# ThirdPartyLogFilter
# ============================================================================

class TestThirdPartyLogFilter:
    """Tests for ThirdPartyLogFilter.filter()."""

    def setup_method(self):
        self.f = ThirdPartyLogFilter()

    def test_filter_allows_refract_logger(self):
        """Records from refract.* are allowed through (return True)."""
        assert self.f.filter(_make_record("refract.registry")) is True
        assert self.f.filter(_make_record("refract.api")) is True
        assert self.f.filter(_make_record("refract")) is True

    def test_filter_allows_root_logger(self):
        """Record from root logger (empty name) is allowed."""
        assert self.f.filter(_make_record("")) is True

    def test_filter_allows_unrelated_third_party(self):
        """A logger that is not in _NOISY_PREFIXES is allowed."""
        assert self.f.filter(_make_record("sqlalchemy")) is True
        assert self.f.filter(_make_record("uvicorn")) is True

    @pytest.mark.parametrize("prefix", _NOISY_PREFIXES)
    def test_filter_blocks_noisy_top_level_prefix(self, prefix):
        """Records whose name exactly matches a noisy prefix are dropped (return False)."""
        assert self.f.filter(_make_record(prefix)) is False

    def test_filter_blocks_asyncio_sublogger(self):
        """asyncio sub-loggers (e.g. asyncio.base_events) are dropped."""
        assert self.f.filter(_make_record("asyncio.base_events")) is False

    def test_filter_blocks_mcp_sublogger(self):
        """mcp sub-loggers (e.g. mcp.server.lowlevel) are dropped."""
        assert self.f.filter(_make_record("mcp.server.lowlevel")) is False

    def test_filter_blocks_httpx_client_sublogger(self):
        """httpx._client sub-logger is dropped."""
        assert self.f.filter(_make_record("httpx._client")) is False

    def test_filter_blocks_httpcore_sublogger(self):
        """httpcore sub-loggers are dropped."""
        assert self.f.filter(_make_record("httpcore.connection")) is False

    def test_filter_blocks_fastapi_mcp_sublogger(self):
        """fastapi_mcp sub-loggers are dropped."""
        assert self.f.filter(_make_record("fastapi_mcp.core")) is False

    def test_filter_blocks_sse_starlette_sublogger(self):
        """sse_starlette sub-loggers are dropped."""
        assert self.f.filter(_make_record("sse_starlette.sse")) is False

    def test_noisy_prefixes_contains_expected_entries(self):
        """_NOISY_PREFIXES includes all expected noisy libraries."""
        expected = {"asyncio", "sse_starlette", "httpcore", "httpx", "mcp", "fastapi_mcp"}
        assert expected.issubset(set(_NOISY_PREFIXES))


# ============================================================================
# configure_cli_logging
# ============================================================================

class TestConfigureCliLogging:
    """Tests for configure_cli_logging(verbose=True/False)."""

    def test_verbose_false_sets_info_level(self):
        """Non-verbose mode sets root logger to INFO."""
        configure_cli_logging(verbose=False)
        assert logging.getLogger().level == logging.INFO

    def test_verbose_true_sets_debug_level(self):
        """Verbose mode sets root logger to DEBUG."""
        configure_cli_logging(verbose=True)
        assert logging.getLogger().level == logging.DEBUG

    def test_default_is_non_verbose(self):
        """Default call (no args) behaves like verbose=False."""
        configure_cli_logging()
        assert logging.getLogger().level == logging.INFO

    def test_adds_third_party_filter_to_root_logger(self):
        """A ThirdPartyLogFilter is attached to the root logger after call."""
        configure_cli_logging(verbose=False)
        root_filters = logging.getLogger().filters
        assert any(isinstance(f, ThirdPartyLogFilter) for f in root_filters)

    def test_refract_logger_level_info_when_not_verbose(self):
        """refract logger level is INFO when verbose=False."""
        configure_cli_logging(verbose=False)
        assert logging.getLogger("refract").level == logging.INFO

    def test_refract_logger_level_debug_when_verbose(self):
        """refract logger level is DEBUG when verbose=True."""
        configure_cli_logging(verbose=True)
        assert logging.getLogger("refract").level == logging.DEBUG

    def test_configure_cli_logging_is_idempotent(self):
        """Calling configure_cli_logging twice does not raise."""
        configure_cli_logging(verbose=False)
        configure_cli_logging(verbose=True)
        assert logging.getLogger().level == logging.DEBUG

    def test_configure_cli_logging_no_duplicate_filters(self):
        """Calling configure_cli_logging multiple times does not add duplicate filters."""
        root = logging.getLogger()
        root.filters = [f for f in root.filters if not isinstance(f, ThirdPartyLogFilter)]

        configure_cli_logging(verbose=False)
        configure_cli_logging(verbose=True)
        configure_cli_logging(verbose=False)

        filter_count = sum(1 for f in root.filters if isinstance(f, ThirdPartyLogFilter))
        assert filter_count == 1


# ============================================================================
# configure_api_logging
# ============================================================================

class TestConfigureApiLogging:
    """Tests for configure_api_logging()."""

    def test_sets_debug_level_on_root_logger(self):
        """configure_api_logging sets root logger to DEBUG."""
        configure_api_logging()
        assert logging.getLogger().level == logging.DEBUG

    def test_adds_third_party_filter(self):
        """A ThirdPartyLogFilter is attached to the root logger."""
        configure_api_logging()
        root_filters = logging.getLogger().filters
        assert any(isinstance(f, ThirdPartyLogFilter) for f in root_filters)

    def test_root_handler_format_includes_timestamp(self):
        """The root logger handler uses a format that includes %(asctime)s."""
        configure_api_logging()
        root_logger = logging.getLogger()
        # basicConfig attaches a StreamHandler to root
        assert len(root_logger.handlers) > 0
        handler = root_logger.handlers[0]
        fmt = handler.formatter._fmt if handler.formatter else ""
        assert "%(asctime)s" in fmt

    def test_configure_api_logging_is_idempotent(self):
        """Calling configure_api_logging twice does not raise."""
        configure_api_logging()
        configure_api_logging()
        assert logging.getLogger().level == logging.DEBUG

    def test_configure_api_logging_no_duplicate_filters(self):
        """Calling configure_api_logging multiple times does not add duplicate filters."""
        root = logging.getLogger()
        root.filters = [f for f in root.filters if not isinstance(f, ThirdPartyLogFilter)]

        configure_api_logging()
        configure_api_logging()
        configure_api_logging()

        filter_count = sum(1 for f in root.filters if isinstance(f, ThirdPartyLogFilter))
        assert filter_count == 1
