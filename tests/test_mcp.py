"""
Tests for refract.mcp module.

All tests operate through Refract instances — there is no global
``create_mcp_app()`` or global registry access in the refract package.
"""
import pytest
from unittest.mock import Mock, patch
from fastapi import FastAPI

from refract.models import FunctionInfo, GenericOutput


# ============================================================================
# REFRACT INSTANCE MCP
# ============================================================================

class TestRefractMcp:
    """Tests for Refract.mcp() and create_mcp_app_for_refract()."""

    def _make_refract(self, name: str = "test-project"):
        """Helper: build an empty Refract instance."""
        from refract.registry import Refract
        return Refract(name)

    # ------------------------------------------------------------------
    # create_mcp_app_for_refract — basic flow
    # ------------------------------------------------------------------

    @patch("refract.mcp._register_mcp_endpoints_for_refract")
    @patch("refract.mcp.FastApiMCP")
    def test_create_mcp_app_for_refract_success(self, mock_fastapi_mcp, mock_register_mcp):
        """create_mcp_app_for_refract returns the same FastAPI app it started from."""
        from refract.mcp import create_mcp_app_for_refract

        r = self._make_refract()
        mock_api_app = Mock(spec=FastAPI)
        mock_api_app.title = "test-project API"
        mock_api_app.description = "API for test-project"
        r.api = Mock(return_value=mock_api_app)

        mock_mcp_instance = Mock()
        mock_fastapi_mcp.return_value = mock_mcp_instance

        result = create_mcp_app_for_refract(r)

        assert result is mock_api_app

    @patch("refract.mcp._register_mcp_endpoints_for_refract")
    @patch("refract.mcp.FastApiMCP")
    def test_create_mcp_app_for_refract_uses_instance_api(self, mock_fastapi_mcp, mock_register):
        """create_mcp_app_for_refract calls refract.api(), not the global create_api_app()."""
        from refract.mcp import create_mcp_app_for_refract

        r = self._make_refract()
        mock_api_app = Mock(spec=FastAPI)
        mock_api_app.title = "original"
        mock_api_app.description = "original"
        r.api = Mock(return_value=mock_api_app)

        mock_fastapi_mcp.return_value = Mock()

        create_mcp_app_for_refract(r)

        # Must use instance api(), NOT some global factory
        r.api.assert_called_once()

    @patch("refract.mcp._register_mcp_endpoints_for_refract")
    @patch("refract.mcp.FastApiMCP")
    def test_create_mcp_app_for_refract_updates_metadata(self, mock_fastapi_mcp, mock_register):
        """create_mcp_app_for_refract sets title/description with instance name."""
        from refract.mcp import create_mcp_app_for_refract

        r = self._make_refract("my-service")
        mock_api_app = Mock(spec=FastAPI)
        mock_api_app.title = "original"
        mock_api_app.description = "original"
        r.api = Mock(return_value=mock_api_app)

        mock_fastapi_mcp.return_value = Mock()

        create_mcp_app_for_refract(r)

        assert mock_api_app.title == "my-service API + MCP Server"
        assert "my-service" in mock_api_app.description

    @patch("refract.mcp._register_mcp_endpoints_for_refract")
    @patch("refract.mcp.FastApiMCP")
    def test_create_mcp_app_for_refract_registers_mcp_endpoints(self, mock_fastapi_mcp, mock_register):
        """create_mcp_app_for_refract calls _register_mcp_endpoints_for_refract."""
        from refract.mcp import create_mcp_app_for_refract

        r = self._make_refract()
        mock_api_app = Mock(spec=FastAPI)
        mock_api_app.title = "t"
        mock_api_app.description = "d"
        r.api = Mock(return_value=mock_api_app)

        mock_fastapi_mcp.return_value = Mock()

        create_mcp_app_for_refract(r)

        mock_register.assert_called_once_with(mock_api_app, r)

    @patch("refract.mcp._register_mcp_endpoints_for_refract")
    @patch("refract.mcp.FastApiMCP")
    def test_create_mcp_app_for_refract_mcp_configuration(self, mock_fastapi_mcp, mock_register):
        """FastApiMCP is initialised with instance-specific name/description."""
        from refract.mcp import create_mcp_app_for_refract

        r = self._make_refract("cool-project")
        mock_api_app = Mock(spec=FastAPI)
        mock_api_app.title = "t"
        mock_api_app.description = "d"
        r.api = Mock(return_value=mock_api_app)

        mock_mcp_instance = Mock()
        mock_fastapi_mcp.return_value = mock_mcp_instance

        create_mcp_app_for_refract(r)

        mock_fastapi_mcp.assert_called_once_with(
            mock_api_app,
            name="cool-project MCP Server",
            description="MCP server for cool-project functions and API endpoints",
            include_tags=["mcp-tools"],
        )
        mock_mcp_instance.mount_http.assert_called_once_with()

    @patch("refract.mcp._register_mcp_endpoints_for_refract")
    @patch("refract.mcp.FastApiMCP")
    def test_create_mcp_app_for_refract_error_raises_runtime(self, mock_fastapi_mcp, mock_register):
        """Errors in create_mcp_app_for_refract are wrapped in RuntimeError."""
        from refract.mcp import create_mcp_app_for_refract

        r = self._make_refract()
        r.api = Mock(side_effect=Exception("api exploded"))

        with pytest.raises(RuntimeError, match="MCP server initialization failed: api exploded"):
            create_mcp_app_for_refract(r)

    @patch("refract.mcp._register_mcp_endpoints_for_refract")
    @patch("refract.mcp.FastApiMCP")
    def test_create_mcp_app_for_refract_exception_chaining(self, mock_fastapi_mcp, mock_register):
        """Original exception is preserved via __cause__."""
        from refract.mcp import create_mcp_app_for_refract

        r = self._make_refract()
        original = ValueError("root cause")
        r.api = Mock(side_effect=original)

        with pytest.raises(RuntimeError) as exc_info:
            create_mcp_app_for_refract(r)

        assert exc_info.value.__cause__ is original

    @patch("refract.mcp._register_mcp_endpoints_for_refract")
    @patch("refract.mcp.FastApiMCP")
    def test_create_mcp_app_mount_error_raises_runtime(self, mock_fastapi_mcp, mock_register):
        """RuntimeError is raised when MCP mount fails."""
        from refract.mcp import create_mcp_app_for_refract

        r = self._make_refract()
        mock_api_app = Mock(spec=FastAPI)
        mock_api_app.title = "t"
        mock_api_app.description = "d"
        r.api = Mock(return_value=mock_api_app)

        mock_mcp_instance = Mock()
        mock_mcp_instance.mount_http.side_effect = Exception("Mount failed")
        mock_fastapi_mcp.return_value = mock_mcp_instance

        with pytest.raises(RuntimeError, match="MCP server initialization failed: Mount failed"):
            create_mcp_app_for_refract(r)

    # ------------------------------------------------------------------
    # _register_mcp_endpoints_for_refract
    # ------------------------------------------------------------------

    def test_register_mcp_endpoints_for_refract_empty_registry(self):
        """With no mcp-interface functions, no routes are added."""
        from refract.mcp import _register_mcp_endpoints_for_refract

        r = self._make_refract()
        mock_app = Mock(spec=FastAPI)

        _register_mcp_endpoints_for_refract(mock_app, r)

        mock_app.add_api_route.assert_not_called()

    def test_register_mcp_endpoints_for_refract_uses_instance_registry(self):
        """Only functions from the Refract instance are registered."""
        from refract.mcp import _register_mcp_endpoints_for_refract

        r = self._make_refract()
        func_info = FunctionInfo(
            name="my_tool",
            func=lambda: None,
            description="A tool",
            params=[],
            http_methods=["POST"],
            interfaces=["mcp"],
            return_type=GenericOutput,
        )
        r._registry.append(func_info)

        mock_app = Mock(spec=FastAPI)

        with patch("refract.mcp.create_handler") as mock_create_handler:
            mock_handler = Mock()
            mock_create_handler.return_value = (mock_handler, Mock())
            _register_mcp_endpoints_for_refract(mock_app, r)

        mock_app.add_api_route.assert_called_once()
        call_kwargs = mock_app.add_api_route.call_args
        assert call_kwargs[0][0] == "/my_tool"
        assert "mcp-tools" in call_kwargs[1]["tags"]

    def test_register_mcp_endpoints_for_refract_skips_non_mcp(self):
        """Functions without 'mcp' interface are not registered as MCP endpoints."""
        from refract.mcp import _register_mcp_endpoints_for_refract

        r = self._make_refract()
        api_only = FunctionInfo(
            name="api_only",
            func=lambda: None,
            description="API only",
            params=[],
            http_methods=["GET"],
            interfaces=["api"],
            return_type=GenericOutput,
        )
        r._registry.append(api_only)

        mock_app = Mock(spec=FastAPI)
        _register_mcp_endpoints_for_refract(mock_app, r)

        mock_app.add_api_route.assert_not_called()

    # ------------------------------------------------------------------
    # Refract.mcp() — delegates to create_mcp_app_for_refract
    # ------------------------------------------------------------------

    @patch("refract.mcp.create_mcp_app_for_refract")
    def test_refract_mcp_delegates_to_create_mcp_app_for_refract(self, mock_create_mcp):
        """Refract.mcp() calls create_mcp_app_for_refract with self."""
        r = self._make_refract()
        mock_app = Mock(spec=FastAPI)
        mock_create_mcp.return_value = mock_app

        result = r.mcp()

        mock_create_mcp.assert_called_once_with(r)
        assert result is mock_app

    @patch("refract.mcp.create_mcp_app_for_refract")
    def test_refract_mcp_returns_fastapi_app(self, mock_create_mcp):
        """Refract.mcp() returns the FastAPI app produced by the factory."""
        r = self._make_refract()
        expected_app = Mock(spec=FastAPI)
        mock_create_mcp.return_value = expected_app

        result = r.mcp()

        assert result is expected_app

    # ------------------------------------------------------------------
    # Error logging
    # ------------------------------------------------------------------

    @patch("refract.mcp._register_mcp_endpoints_for_refract")
    @patch("refract.mcp.FastApiMCP")
    @patch("refract.mcp.logger")
    def test_create_mcp_app_logs_success(self, mock_logger, mock_fastapi_mcp, mock_register):
        """Successful MCP app creation is logged at INFO level."""
        from refract.mcp import create_mcp_app_for_refract

        r = self._make_refract("my-app")
        mock_api_app = Mock(spec=FastAPI)
        mock_api_app.title = "t"
        mock_api_app.description = "d"
        r.api = Mock(return_value=mock_api_app)
        mock_fastapi_mcp.return_value = Mock()

        create_mcp_app_for_refract(r)

        # Should log success
        mock_logger.info.assert_called()
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("Successfully created MCP app" in c for c in info_calls)

    @patch("refract.mcp._register_mcp_endpoints_for_refract")
    @patch("refract.mcp.FastApiMCP")
    @patch("refract.mcp.logger")
    def test_create_mcp_app_logs_error(self, mock_logger, mock_fastapi_mcp, mock_register):
        """Errors during MCP app creation are logged at ERROR level."""
        from refract.mcp import create_mcp_app_for_refract

        r = self._make_refract()
        r.api = Mock(side_effect=Exception("something broke"))

        with pytest.raises(RuntimeError):
            create_mcp_app_for_refract(r)

        mock_logger.error.assert_called()
        error_calls = [str(c) for c in mock_logger.error.call_args_list]
        assert any("something broke" in c for c in error_calls)

    # ------------------------------------------------------------------
    # Isolation: two Refract instances
    # ------------------------------------------------------------------

    @patch("refract.mcp._register_mcp_endpoints_for_refract")
    @patch("refract.mcp.FastApiMCP")
    def test_two_refract_instances_get_independent_mcp_apps(self, mock_fastapi_mcp, mock_register):
        """Each Refract instance produces a separate MCP app."""
        from refract.mcp import create_mcp_app_for_refract

        app_a = Mock(spec=FastAPI)
        app_a.title = "a"
        app_a.description = "a"
        app_b = Mock(spec=FastAPI)
        app_b.title = "b"
        app_b.description = "b"

        r1 = self._make_refract("project-a")
        r1.api = Mock(return_value=app_a)

        r2 = self._make_refract("project-b")
        r2.api = Mock(return_value=app_b)

        mock_fastapi_mcp.return_value = Mock()

        result_a = create_mcp_app_for_refract(r1)
        result_b = create_mcp_app_for_refract(r2)

        assert result_a is app_a
        assert result_b is app_b
        assert result_a is not result_b
        assert app_a.title == "project-a API + MCP Server"
        assert app_b.title == "project-b API + MCP Server"

    # ------------------------------------------------------------------
    # Module-level assertions
    # ------------------------------------------------------------------

    def test_module_exports(self):
        """refract.mcp exposes the expected public symbols."""
        import refract.mcp as mcp_module

        assert hasattr(mcp_module, "create_mcp_app_for_refract")
        assert hasattr(mcp_module, "_register_mcp_endpoints_for_refract")
        assert hasattr(mcp_module, "FastAPI")
        assert hasattr(mcp_module, "FastApiMCP")
        assert hasattr(mcp_module, "logger")

    def test_logger_name(self):
        """Module logger is named 'refract.mcp'."""
        from refract.mcp import logger
        assert logger.name == "refract.mcp"

    def test_module_docstring(self):
        """Module docstring mentions MCP and Model Context Protocol."""
        import refract.mcp as mcp_module
        assert mcp_module.__doc__ is not None
        assert "MCP" in mcp_module.__doc__
        assert "Model Context Protocol" in mcp_module.__doc__
