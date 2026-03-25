"""
Pytest configuration and global fixtures for refract tests.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from typing import Any
import logging

from pydantic import BaseModel
from refract.models import ParamSchema, FunctionInfo
from refract.registry import _clear_pending

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)


class TestOutput(BaseModel):
    """Local test model replacing GenericOutput. Used across all tests."""
    result: Any
    success: bool = True
    message: str | None = None


@pytest.fixture(autouse=True)
def cleanup_registry():
    """Automatically clear pending buffer before and after each test to ensure isolation."""
    _clear_pending()
    yield
    _clear_pending()


@pytest.fixture
def sample_function():
    """Sample function for testing registry functionality."""
    def test_add(x: int, y: int = 1) -> TestOutput:
        """Add two numbers together.

        Args:
            x: First number
            y: Second number (defaults to 1)

        Returns:
            Sum of x and y
        """
        return TestOutput(result=x + y, success=True)
    return test_add


@pytest.fixture
def sample_explicit_param():
    """Sample ParamSchema for testing."""
    return ParamSchema(
        name="test_param",
        type=int,
        default=None,
        required=True,
        description="A test parameter"
    )


@pytest.fixture
def sample_function_info(sample_function):
    """Sample FunctionInfo for testing."""
    return FunctionInfo(
        name="test_add",
        func=sample_function,
        description="Add two numbers together",
        params=[
            ParamSchema(name="x", type=int, required=True, description="First number"),
            ParamSchema(name="y", type=int, default=1, required=False, description="Second number")
        ],
        http_methods=["GET", "POST"],
        return_type=TestOutput
    )


@pytest.fixture
def async_sample_function_info():
    """Sample async FunctionInfo for testing async handler support."""
    async def async_test_add(x: int, y: int = 1) -> TestOutput:
        return TestOutput(result=x + y, success=True)

    return FunctionInfo(
        name="async_test_add",
        func=async_test_add,
        description="Async add two numbers",
        params=[
            ParamSchema(name="x", type=int, required=True, description="First number"),
            ParamSchema(name="y", type=int, default=1, required=False, description="Second number"),
        ],
        http_methods=["GET", "POST"],
        return_type=TestOutput,
    )


@pytest.fixture
def mock_uvicorn():
    """Mock uvicorn.run for CLI testing."""
    with patch('uvicorn.run') as mock_run:
        yield mock_run


@pytest.fixture
def mock_fastapi_app():
    """Mock FastAPI app for testing."""
    app = MagicMock()
    app.add_api_route = Mock()
    app.mount = Mock()
    app.routes = []
    return app


@pytest.fixture
def api_test_params():
    """Common test parameters for API testing."""
    return {
        "valid_params": {"x": 5, "y": 3},
        "invalid_params": {"x": "not_int", "y": 3},
        "missing_required": {"y": 3},
        "with_defaults": {"x": 5}
    }


@pytest.fixture
def cli_test_context():
    """Click testing context for CLI tests."""
    from click.testing import CliRunner
    return CliRunner()


@pytest.fixture
def mock_logger():
    """Mock logger for testing logging behavior."""
    with patch('logging.getLogger') as mock_get_logger:
        mock_logger_instance = Mock()
        mock_get_logger.return_value = mock_logger_instance
        yield mock_logger_instance


@pytest.fixture
def fastapi_test_client():
    """FastAPI test client factory."""
    def _create_test_client(app):
        from fastapi.testclient import TestClient
        return TestClient(app)
    return _create_test_client
