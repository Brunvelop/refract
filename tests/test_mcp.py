"""
Tests for refract.mcp module.

All tests operate through Refract instances — there is no global
``create_mcp_app()`` or global registry access in the refract package.
"""
import pytest
from unittest.mock import Mock, patch
from fastapi import FastAPI

from refract.models import FunctionInfo
from tests.conftest import TestOutput


# ============================================================================
# REFRACT INSTANCE MCP
# ============================================================================

class TestRefractMcp:
    """Tests for Refract.mcp() and create_mcp_app()."""

    def _make_refract(self, name: str = "test-project"):
        """Helper: build an empty Refract instance."""
        from refract import Refract
        return Refract(name)

    # ------------------------------------------------------------------
    # create_mcp_app — basic flow
    # ------------------------------------------------------------------

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    @patch("refract.mcp.create_api_app")
    def test_create_mcp_app_success(self, mock_create_api, mock_fastapi_mcp, mock_register_mcp):
        """create_mcp_app returns the same FastAPI app it started from."""
        from refract.mcp import create_mcp_app

        r = self._make_refract()
        mock_api_app = Mock(spec=FastAPI)
        mock_api_app.title = "test-project API"
        mock_api_app.description = "API for test-project"
        mock_create_api.return_value = mock_api_app

        mock_mcp_instance = Mock()
        mock_fastapi_mcp.return_value = mock_mcp_instance

        result = create_mcp_app(r)

        assert result is mock_api_app

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    @patch("refract.mcp.create_api_app")
    def test_create_mcp_app_uses_instance_api(self, mock_create_api, mock_fastapi_mcp, mock_register):
        """create_mcp_app calls create_api_app(registry), bound to the instance."""
        from refract.mcp import create_mcp_app

        r = self._make_refract()
        mock_api_app = Mock(spec=FastAPI)
        mock_api_app.title = "original"
        mock_api_app.description = "original"
        mock_create_api.return_value = mock_api_app

        mock_fastapi_mcp.return_value = Mock()

        create_mcp_app(r)

        # Must call create_api_app with the instance
        mock_create_api.assert_called_once_with(r)

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    @patch("refract.mcp.create_api_app")
    def test_create_mcp_app_updates_metadata(self, mock_create_api, mock_fastapi_mcp, mock_register):
        """create_mcp_app sets title/description with instance name."""
        from refract.mcp import create_mcp_app

        r = self._make_refract("my-service")
        mock_api_app = Mock(spec=FastAPI)
        mock_api_app.title = "original"
        mock_api_app.description = "original"
        mock_create_api.return_value = mock_api_app

        mock_fastapi_mcp.return_value = Mock()

        create_mcp_app(r)

        assert mock_api_app.title == "my-service API + MCP Server"
        assert "my-service" in mock_api_app.description

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    @patch("refract.mcp.create_api_app")
    def test_create_mcp_app_registers_mcp_endpoints(self, mock_create_api, mock_fastapi_mcp, mock_register):
        """create_mcp_app calls _register_mcp_endpoints."""
        from refract.mcp import create_mcp_app

        r = self._make_refract()
        mock_api_app = Mock(spec=FastAPI)
        mock_api_app.title = "t"
        mock_api_app.description = "d"
        mock_create_api.return_value = mock_api_app

        mock_fastapi_mcp.return_value = Mock()

        create_mcp_app(r)

        mock_register.assert_called_once_with(mock_api_app, r)

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    @patch("refract.mcp.create_api_app")
    def test_create_mcp_app_mcp_configuration(self, mock_create_api, mock_fastapi_mcp, mock_register):
        """FastApiMCP is initialised with instance-specific name/description."""
        from refract.mcp import create_mcp_app

        r = self._make_refract("cool-project")
        mock_api_app = Mock(spec=FastAPI)
        mock_api_app.title = "t"
        mock_api_app.description = "d"
        mock_create_api.return_value = mock_api_app

        mock_mcp_instance = Mock()
        mock_fastapi_mcp.return_value = mock_mcp_instance

        create_mcp_app(r)

        mock_fastapi_mcp.assert_called_once_with(
            mock_api_app,
            name="cool-project MCP Server",
            description="MCP server for cool-project functions and API endpoints",
            include_tags=["mcp-tools"],
        )
        mock_mcp_instance.mount_http.assert_called_once_with()

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    @patch("refract.mcp.create_api_app")
    def test_create_mcp_app_error_raises_runtime(self, mock_create_api, mock_fastapi_mcp, mock_register):
        """Errors in create_mcp_app are wrapped in RuntimeError."""
        from refract.mcp import create_mcp_app

        r = self._make_refract()
        mock_create_api.side_effect = Exception("api exploded")

        with pytest.raises(RuntimeError, match="MCP server initialization failed: api exploded"):
            create_mcp_app(r)

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    @patch("refract.mcp.create_api_app")
    def test_create_mcp_app_exception_chaining(self, mock_create_api, mock_fastapi_mcp, mock_register):
        """Original exception is preserved via __cause__."""
        from refract.mcp import create_mcp_app

        r = self._make_refract()
        original = ValueError("root cause")
        mock_create_api.side_effect = original

        with pytest.raises(RuntimeError) as exc_info:
            create_mcp_app(r)

        assert exc_info.value.__cause__ is original

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    @patch("refract.mcp.create_api_app")
    def test_create_mcp_app_mount_error_raises_runtime(self, mock_create_api, mock_fastapi_mcp, mock_register):
        """RuntimeError is raised when MCP mount fails."""
        from refract.mcp import create_mcp_app

        r = self._make_refract()
        mock_api_app = Mock(spec=FastAPI)
        mock_api_app.title = "t"
        mock_api_app.description = "d"
        mock_create_api.return_value = mock_api_app

        mock_mcp_instance = Mock()
        mock_mcp_instance.mount_http.side_effect = Exception("Mount failed")
        mock_fastapi_mcp.return_value = mock_mcp_instance

        with pytest.raises(RuntimeError, match="MCP server initialization failed: Mount failed"):
            create_mcp_app(r)

    # ------------------------------------------------------------------
    # _register_mcp_endpoints
    # ------------------------------------------------------------------

    def test_register_mcp_endpoints_empty_registry(self):
        """With no mcp-interface functions, no routes are added."""
        from refract.mcp import _register_mcp_endpoints

        r = self._make_refract()
        mock_app = Mock(spec=FastAPI)

        _register_mcp_endpoints(mock_app, r)

        mock_app.add_api_route.assert_not_called()

    def test_register_mcp_endpoints_uses_instance_registry(self):
        """Only functions from the Refract instance are registered."""
        from refract.mcp import _register_mcp_endpoints

        r = self._make_refract()
        func_info = FunctionInfo(
            name="my_tool",
            func=lambda: None,
            description="A tool",
            params=[],
            http_methods=["POST"],
            interfaces=["mcp"],
            return_type=TestOutput,
        )
        r._registry.append(func_info)

        mock_app = Mock(spec=FastAPI)

        with patch("refract.mcp.create_handler") as mock_create_handler:
            mock_handler = Mock()
            mock_create_handler.return_value = (mock_handler, Mock())
            _register_mcp_endpoints(mock_app, r)

        mock_app.add_api_route.assert_called_once()
        call_kwargs = mock_app.add_api_route.call_args
        assert call_kwargs[0][0] == "/my_tool"
        assert "mcp-tools" in call_kwargs[1]["tags"]

    def test_register_mcp_endpoints_skips_non_mcp(self):
        """Functions without 'mcp' interface are not registered as MCP endpoints."""
        from refract.mcp import _register_mcp_endpoints

        r = self._make_refract()
        api_only = FunctionInfo(
            name="api_only",
            func=lambda: None,
            description="API only",
            params=[],
            http_methods=["GET"],
            interfaces=["api"],
            return_type=TestOutput,
        )
        r._registry.append(api_only)

        mock_app = Mock(spec=FastAPI)
        _register_mcp_endpoints(mock_app, r)

        mock_app.add_api_route.assert_not_called()

    # ------------------------------------------------------------------
    # Refract.mcp() — delegates to create_mcp_app
    # ------------------------------------------------------------------

    @patch("refract.refract.create_mcp_app")
    def test_refract_mcp_delegates_to_create_mcp_app(self, mock_create_mcp):
        """Refract.mcp() calls create_mcp_app with self."""
        r = self._make_refract()
        mock_app = Mock(spec=FastAPI)
        mock_create_mcp.return_value = mock_app

        result = r.mcp()

        mock_create_mcp.assert_called_once_with(r)
        assert result is mock_app

    @patch("refract.refract.create_mcp_app")
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

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    @patch("refract.mcp.logger")
    @patch("refract.mcp.create_api_app")
    def test_create_mcp_app_logs_success(self, mock_create_api, mock_logger, mock_fastapi_mcp, mock_register):
        """Successful MCP app creation is logged at INFO level."""
        from refract.mcp import create_mcp_app

        r = self._make_refract("my-app")
        mock_api_app = Mock(spec=FastAPI)
        mock_api_app.title = "t"
        mock_api_app.description = "d"
        mock_create_api.return_value = mock_api_app
        mock_fastapi_mcp.return_value = Mock()

        create_mcp_app(r)

        # Should log success
        mock_logger.info.assert_called()
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("Successfully created MCP app" in c for c in info_calls)

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    @patch("refract.mcp.logger")
    @patch("refract.mcp.create_api_app")
    def test_create_mcp_app_logs_error(self, mock_create_api, mock_logger, mock_fastapi_mcp, mock_register):
        """Errors during MCP app creation are logged at ERROR level."""
        from refract.mcp import create_mcp_app

        r = self._make_refract()
        mock_create_api.side_effect = Exception("something broke")

        with pytest.raises(RuntimeError):
            create_mcp_app(r)

        mock_logger.error.assert_called()
        error_calls = [str(c) for c in mock_logger.error.call_args_list]
        assert any("something broke" in c for c in error_calls)

    # ------------------------------------------------------------------
    # Isolation: two Refract instances
    # ------------------------------------------------------------------

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    @patch("refract.mcp.create_api_app")
    def test_two_refract_instances_get_independent_mcp_apps(self, mock_create_api, mock_fastapi_mcp, mock_register):
        """Each Refract instance produces a separate MCP app."""
        from refract.mcp import create_mcp_app

        app_a = Mock(spec=FastAPI)
        app_a.title = "a"
        app_a.description = "a"
        app_b = Mock(spec=FastAPI)
        app_b.title = "b"
        app_b.description = "b"

        r1 = self._make_refract("project-a")
        r2 = self._make_refract("project-b")

        mock_create_api.side_effect = [app_a, app_b]
        mock_fastapi_mcp.return_value = Mock()

        result_a = create_mcp_app(r1)
        result_b = create_mcp_app(r2)

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

        assert hasattr(mcp_module, "create_mcp_app")
        assert hasattr(mcp_module, "create_mcp_only_app")
        assert hasattr(mcp_module, "_register_mcp_endpoints")
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


# ============================================================================
# create_mcp_only_app
# ============================================================================

class TestCreateMcpOnlyApp:
    """Tests for create_mcp_only_app() — MCP-only server."""

    def _make_refract(self, name: str = "test-project"):
        from refract import Refract
        return Refract(name)

    # ------------------------------------------------------------------
    # Basic flow
    # ------------------------------------------------------------------

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    def test_create_mcp_only_app_returns_fastapi_app(self, mock_fastapi_mcp, mock_register):
        """create_mcp_only_app returns a FastAPI instance."""
        from refract.mcp import create_mcp_only_app

        mock_fastapi_mcp.return_value = Mock()
        r = self._make_refract()
        result = create_mcp_only_app(r)

        assert isinstance(result, FastAPI)

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    @patch("refract.mcp.create_api_app")
    def test_create_mcp_only_app_does_not_call_create_api_app(
        self, mock_create_api, mock_fastapi_mcp, mock_register
    ):
        """create_mcp_only_app must NOT delegate to create_api_app."""
        from refract.mcp import create_mcp_only_app

        mock_fastapi_mcp.return_value = Mock()
        r = self._make_refract()
        create_mcp_only_app(r)

        mock_create_api.assert_not_called()

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    def test_create_mcp_only_app_calls_register_mcp_endpoints(self, mock_fastapi_mcp, mock_register):
        """create_mcp_only_app calls _register_mcp_endpoints with the new app and registry."""
        from refract.mcp import create_mcp_only_app

        mock_fastapi_mcp.return_value = Mock()
        r = self._make_refract()
        result = create_mcp_only_app(r)

        mock_register.assert_called_once()
        call_args = mock_register.call_args
        assert call_args[0][0] is result  # first arg is the app
        assert call_args[0][1] is r       # second arg is the registry

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    def test_create_mcp_only_app_sets_title_with_registry_name(self, mock_fastapi_mcp, mock_register):
        """The app title includes the registry name."""
        from refract.mcp import create_mcp_only_app

        mock_fastapi_mcp.return_value = Mock()
        r = self._make_refract("cool-service")
        result = create_mcp_only_app(r)

        assert "cool-service" in result.title

    # ------------------------------------------------------------------
    # Health endpoint
    # ------------------------------------------------------------------

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    def test_create_mcp_only_app_has_health_route(self, mock_fastapi_mcp, mock_register):
        """create_mcp_only_app registers a /health route."""
        from refract.mcp import create_mcp_only_app

        mock_fastapi_mcp.return_value = Mock()
        r = self._make_refract()
        result = create_mcp_only_app(r)

        routes = [route.path for route in result.routes]
        assert "/health" in routes

    # ------------------------------------------------------------------
    # FastApiMCP configuration
    # ------------------------------------------------------------------

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    def test_create_mcp_only_app_configures_fastapi_mcp(self, mock_fastapi_mcp, mock_register):
        """FastApiMCP is initialised with include_tags=['mcp-tools']."""
        from refract.mcp import create_mcp_only_app

        mock_mcp_instance = Mock()
        mock_fastapi_mcp.return_value = mock_mcp_instance
        r = self._make_refract("my-svc")
        create_mcp_only_app(r)

        mock_fastapi_mcp.assert_called_once()
        _, kwargs = mock_fastapi_mcp.call_args
        assert kwargs["include_tags"] == ["mcp-tools"]
        assert "my-svc" in kwargs["name"]

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    def test_create_mcp_only_app_calls_mount_http(self, mock_fastapi_mcp, mock_register):
        """FastApiMCP.mount_http() is called."""
        from refract.mcp import create_mcp_only_app

        mock_mcp_instance = Mock()
        mock_fastapi_mcp.return_value = mock_mcp_instance
        r = self._make_refract()
        create_mcp_only_app(r)

        mock_mcp_instance.mount_http.assert_called_once_with()

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    def test_create_mcp_only_app_mount_error_raises_runtime(self, mock_fastapi_mcp, mock_register):
        """RuntimeError is raised (with chaining) when MCP mount fails."""
        from refract.mcp import create_mcp_only_app

        mock_mcp_instance = Mock()
        mock_mcp_instance.mount_http.side_effect = Exception("mount boom")
        mock_fastapi_mcp.return_value = mock_mcp_instance
        r = self._make_refract()

        with pytest.raises(RuntimeError, match="MCP server initialization failed: mount boom"):
            create_mcp_only_app(r)

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    def test_create_mcp_only_app_error_chains_cause(self, mock_fastapi_mcp, mock_register):
        """Original exception is preserved via __cause__."""
        from refract.mcp import create_mcp_only_app

        original = ValueError("original cause")
        mock_mcp_instance = Mock()
        mock_mcp_instance.mount_http.side_effect = original
        mock_fastapi_mcp.return_value = mock_mcp_instance
        r = self._make_refract()

        with pytest.raises(RuntimeError) as exc_info:
            create_mcp_only_app(r)

        assert exc_info.value.__cause__ is original

    # ------------------------------------------------------------------
    # Isolation: two Refract instances
    # ------------------------------------------------------------------

    @patch("refract.mcp._register_mcp_endpoints")
    @patch("refract.mcp.FastApiMCP")
    def test_two_instances_produce_independent_mcp_only_apps(self, mock_fastapi_mcp, mock_register):
        """Each Refract instance produces a separate MCP-only app."""
        from refract.mcp import create_mcp_only_app

        mock_fastapi_mcp.return_value = Mock()
        r1 = self._make_refract("svc-a")
        r2 = self._make_refract("svc-b")

        app1 = create_mcp_only_app(r1)
        app2 = create_mcp_only_app(r2)

        assert app1 is not app2
        assert "svc-a" in app1.title
        assert "svc-b" in app2.title

    # ------------------------------------------------------------------
    # Refract.mcp_only() — delegates to create_mcp_only_app
    # ------------------------------------------------------------------

    @patch("refract.refract.create_mcp_only_app")
    def test_refract_mcp_only_delegates(self, mock_factory):
        """Refract.mcp_only() calls create_mcp_only_app with self."""
        from refract import Refract

        r = Refract("test-project")
        expected = Mock(spec=FastAPI)
        mock_factory.return_value = expected

        result = r.mcp_only()

        mock_factory.assert_called_once_with(r)
        assert result is expected
