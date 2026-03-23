"""
Tests for refract.api module.

Tests the FastAPI server functionality including dynamic endpoint generation,
request/response handling, and integration with the Refract instance registry.
"""
import pytest
import asyncio
import os
import tempfile
from typing import Dict, Any, List
from unittest.mock import Mock, patch, MagicMock
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from refract.api import (
    _format_response,
    _create_dynamic_model,
    _extract_params,
    _execute_function,
    create_handler,
    _register_static_files,
    create_router_for_refract,
    create_api_app_for_refract,
    _add_function_endpoints,
    _register_standard_endpoints_for_refract,
)
from refract.models import GenericOutput, FunctionInfo, ParamSchema
from refract.registry import _registry, clear_registry, Refract


# ---------------------------------------------------------------------------
# Aliases for backward compat (keep test names from original test_api.py)
# ---------------------------------------------------------------------------
create_result_response = _format_response
create_dynamic_model = _create_dynamic_model
extract_function_params = _extract_params
execute_function_with_params = _execute_function


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_refract_stub(functions=None, stream_registry=None):
    """Build a minimal Refract-like stub for use in router/api tests."""
    stub = Refract("test-stub")
    if functions:
        stub._registry.extend(functions)
    if stream_registry:
        stub._stream_registry.update(stream_registry)
    return stub


def _make_api_func_info(name="api_func", http_methods=None):
    """Create a simple FunctionInfo with 'api' interface."""
    def _fn(x: int, y: int = 1) -> GenericOutput:
        return GenericOutput(result=x + y, success=True)

    _fn.__name__ = name
    return FunctionInfo(
        name=name,
        func=_fn,
        description=f"Test function {name}",
        params=[
            ParamSchema(name="x", type=int, required=True, description="x"),
            ParamSchema(name="y", type=int, default=1, required=False, description="y"),
        ],
        http_methods=http_methods or ["GET", "POST"],
        interfaces=["api"],
        return_type=GenericOutput,
    )


# ---------------------------------------------------------------------------
# Tests: _format_response (create_result_response)
# ---------------------------------------------------------------------------

class TestCreateResultResponse:
    """Tests for _format_response — result formatting."""

    def test_create_result_response_dict(self):
        """Test response creation with dict input (should return as-is)."""
        input_dict = {"key": "value", "number": 42, "nested": {"inner": "data"}}
        result = create_result_response(input_dict)

        assert result == input_dict
        assert isinstance(result, dict)

    @pytest.mark.parametrize("input_value,expected_result", [
        ("string_result", "string_result"),
        (123, 123),
        (True, True),
        (None, None),
        ([1, 2, 3], [1, 2, 3]),
    ])
    def test_create_result_response_non_dict(self, input_value, expected_result):
        """Test response creation with non-dict inputs via GenericOutput wrapper."""
        generic_output = GenericOutput(result=input_value, success=True)
        result = create_result_response(generic_output)

        assert isinstance(result, dict)
        assert "result" in result
        assert result["result"] == expected_result
        assert "success" in result
        assert result["success"] is True
        assert "message" in result
        assert result["message"] is None

    def test_create_result_response_complex_object(self):
        """Test response creation with complex object."""
        class CustomObject:
            def __init__(self, value):
                self.value = value

        obj = CustomObject("test")
        generic_output = GenericOutput(result=obj, success=True)
        result = create_result_response(generic_output)

        assert isinstance(result, dict)
        assert result["result"] == obj


class TestCreateResultResponseBaseModel:
    """Tests for _format_response with custom BaseModel subclasses."""

    def test_format_response_custom_basemodel_returns_model_dump(self):
        """Any BaseModel subclass is serialized via .model_dump()."""
        class SearchResponse(BaseModel):
            users: list
            total: int

        result = SearchResponse(users=["ana", "bob"], total=2)
        response = create_result_response(result)

        assert isinstance(response, dict)
        assert response["users"] == ["ana", "bob"]
        assert response["total"] == 2

    def test_format_response_basemodel_with_optional_fields(self):
        """BaseModel with optional fields serializes correctly."""
        from typing import Optional as Opt

        class RichResponse(BaseModel):
            value: int
            label: str
            notes: Opt[str] = None

        result = RichResponse(value=42, label="ok")
        response = create_result_response(result)

        assert response["value"] == 42
        assert response["label"] == "ok"
        assert response["notes"] is None

    def test_format_response_non_basemodel_non_dict_falls_back_to_generic_output(self):
        """Non-BaseModel, non-dict results fall back to GenericOutput with warning."""
        class CustomObject:
            def __init__(self, val):
                self.val = val

        obj = CustomObject("test")
        response = create_result_response(obj)

        assert isinstance(response, dict)
        assert response["success"] is False
        assert "non-BaseModel type" in response["message"]
        assert "CustomObject" in response["message"]

    def test_format_response_generic_output_still_works_via_basemodel_path(self):
        """GenericOutput is handled correctly (via BaseModel isinstance check)."""
        output = GenericOutput(result=99, success=True, message="all good")
        response = create_result_response(output)

        assert response["result"] == 99
        assert response["success"] is True
        assert response["message"] == "all good"


class TestCreateResultResponseExtended:
    """Extended edge-case tests for _format_response."""

    def test_create_result_response_nested_dict(self):
        """Test response creation with deeply nested dict."""
        nested_dict = {
            "level1": {
                "level2": {
                    "level3": ["item1", "item2"],
                    "level3_dict": {"key": "value"},
                },
                "numbers": [1, 2, 3, 4, 5],
            },
            "root_key": "root_value",
        }
        result = create_result_response(nested_dict)

        assert result == nested_dict
        assert result["level1"]["level2"]["level3"] == ["item1", "item2"]

    def test_create_result_response_empty_containers(self):
        """Test response creation with empty containers."""
        result_dict = create_result_response({})
        assert result_dict == {}

        empty_list_output = GenericOutput(result=[], success=True)
        result_list = create_result_response(empty_list_output)
        assert result_list["result"] == []
        assert result_list["success"] is True

    def test_create_result_response_mixed_types(self):
        """Test response creation with mixed data types."""
        mixed_data = {
            "string": "text",
            "integer": 42,
            "float": 3.14,
            "boolean": True,
            "none": None,
            "list": [1, "two", 3.0, False],
            "nested": {"inner": "value"},
        }
        result = create_result_response(mixed_data)

        assert result == mixed_data
        assert result["list"] == [1, "two", 3.0, False]


# ---------------------------------------------------------------------------
# Tests: _create_dynamic_model
# ---------------------------------------------------------------------------

class TestCreateDynamicModel:
    """Tests for _create_dynamic_model — Pydantic model generation."""

    def test_create_dynamic_model_post_required_only(self):
        """Test creating POST model with required parameters only."""
        required_param = ParamSchema(
            name="required_param",
            type=str,
            required=True,
            description="A required parameter",
        )
        func_info = FunctionInfo(
            name="test_func",
            func=lambda x: x,
            description="Test",
            params=[required_param],
            return_type=GenericOutput,
        )

        DynamicModel = create_dynamic_model(func_info, for_post=True)

        assert DynamicModel.__name__ == "Test_FuncInput"
        instance = DynamicModel(required_param="test_value")
        assert instance.required_param == "test_value"

        with pytest.raises(Exception):
            DynamicModel()

    def test_create_dynamic_model_post_with_optional(self, sample_function_info):
        """Test creating POST model with optional parameters."""
        DynamicModel = create_dynamic_model(sample_function_info, for_post=True)

        assert DynamicModel.__name__ == "Test_AddInput"
        instance = DynamicModel(x=5, y=3)
        assert instance.x == 5
        assert instance.y == 3

        instance = DynamicModel(x=5)
        assert instance.x == 5
        assert instance.y == 1  # Default value

    def test_create_dynamic_model_get(self, sample_function_info):
        """Test creating GET model (query parameters)."""
        DynamicModel = create_dynamic_model(sample_function_info, for_post=False)

        assert DynamicModel.__name__ == "Test_AddQueryParams"
        instance = DynamicModel(x=10)
        assert instance.x == 10
        assert instance.y == 1

    def test_create_dynamic_model_complex_types(self):
        """Test creating model with various parameter types."""
        params = [
            ParamSchema(name="str_param", type=str, required=True, description="String param"),
            ParamSchema(name="int_param", type=int, default=42, required=False, description="Int param"),
            ParamSchema(name="bool_param", type=bool, default=True, required=False, description="Bool param"),
        ]

        func_info = FunctionInfo(
            name="complex_func",
            func=lambda: None,
            description="Complex function",
            params=params,
            return_type=GenericOutput,
        )

        DynamicModel = create_dynamic_model(func_info, for_post=True)

        instance = DynamicModel(str_param="test")
        assert instance.str_param == "test"
        assert instance.int_param == 42
        assert instance.bool_param is True

    def test_create_dynamic_model_with_list_type(self):
        """Test creating model with List type parameter."""
        params = [
            ParamSchema(name="items", type=List[str], required=True, description="List of items"),
            ParamSchema(name="numbers", type=List[int], default=[], required=False, description="Numbers"),
        ]

        func_info = FunctionInfo(
            name="list_func",
            func=lambda items, numbers: None,
            description="Function with list parameters",
            params=params,
            return_type=GenericOutput,
        )

        DynamicModel = create_dynamic_model(func_info, for_post=True)

        instance = DynamicModel(items=["a", "b"], numbers=[1, 2])
        assert instance.items == ["a", "b"]
        assert instance.numbers == [1, 2]

        instance = DynamicModel(items=["x"])
        assert instance.numbers == []

    def test_create_dynamic_model_with_dict_type(self):
        """Test creating model with Dict type parameter."""
        params = [
            ParamSchema(name="config", type=Dict[str, Any], required=True, description="Config"),
            ParamSchema(name="metadata", type=Dict[str, str], default={}, required=False, description="Meta"),
        ]

        func_info = FunctionInfo(
            name="dict_func",
            func=lambda config, metadata: None,
            description="Dict function",
            params=params,
            return_type=GenericOutput,
        )

        DynamicModel = create_dynamic_model(func_info, for_post=True)

        instance = DynamicModel(config={"k": "v"}, metadata={"a": "b"})
        assert instance.config == {"k": "v"}
        assert instance.metadata == {"a": "b"}

        instance = DynamicModel(config={"minimal": "config"})
        assert instance.metadata == {}

    def test_create_dynamic_model_all_optional_params(self):
        """Test creating model with all optional parameters."""
        params = [
            ParamSchema(name="opt1", type=str, default="default1", required=False, description="Opt1"),
            ParamSchema(name="opt2", type=int, default=100, required=False, description="Opt2"),
            ParamSchema(name="opt3", type=bool, default=False, required=False, description="Opt3"),
        ]

        func_info = FunctionInfo(
            name="all_optional_func",
            func=lambda opt1, opt2, opt3: None,
            description="All optional",
            params=params,
            return_type=GenericOutput,
        )

        DynamicModel = create_dynamic_model(func_info, for_post=True)

        instance = DynamicModel()
        assert instance.opt1 == "default1"
        assert instance.opt2 == 100
        assert instance.opt3 is False

        instance = DynamicModel(opt2=200, opt3=True)
        assert instance.opt1 == "default1"
        assert instance.opt2 == 200
        assert instance.opt3 is True

    def test_create_dynamic_model_no_params(self):
        """Test creating model with no parameters."""
        func_info = FunctionInfo(
            name="no_params_func",
            func=lambda: "result",
            description="No params",
            params=[],
            return_type=GenericOutput,
        )

        DynamicModel = create_dynamic_model(func_info, for_post=True)
        instance = DynamicModel()
        assert instance is not None


# ---------------------------------------------------------------------------
# Tests: _extract_params
# ---------------------------------------------------------------------------

class TestExtractFunctionParams:
    """Tests for _extract_params — parameter extraction."""

    def test_extract_function_params_all_present(self, sample_function_info):
        result = extract_function_params(sample_function_info, {"x": 5, "y": 3})
        assert result == {"x": 5, "y": 3}

    def test_extract_function_params_missing_optional(self, sample_function_info):
        result = extract_function_params(sample_function_info, {"x": 5})
        assert result == {"x": 5, "y": 1}

    def test_extract_function_params_missing_required(self, sample_function_info):
        result = extract_function_params(sample_function_info, {"y": 3})
        assert result == {"y": 3}

    def test_extract_function_params_extra_params(self, sample_function_info):
        result = extract_function_params(sample_function_info, {"x": 5, "y": 3, "extra": "ignored"})
        assert result == {"x": 5, "y": 3}

    def test_extract_function_params_none_defaults(self):
        params = [
            ParamSchema(name="required", type=str, required=True, description="Required"),
            ParamSchema(name="optional", type=str, default=None, required=False, description="Optional"),
        ]
        func_info = FunctionInfo(
            name="test",
            func=lambda: None,
            description="Test",
            params=params,
            return_type=GenericOutput,
        )

        result = extract_function_params(func_info, {"required": "test"})
        assert result == {"required": "test"}

    def test_extract_function_params_mixed_defaults(self):
        """Test parameter extraction with mixed default types."""
        params = [
            ParamSchema(name="required_str", type=str, required=True, description="Required"),
            ParamSchema(name="optional_int", type=int, default=42, required=False, description="Int"),
            ParamSchema(name="optional_list", type=List[str], default=[], required=False, description="List"),
            ParamSchema(name="optional_dict", type=Dict[str, Any], default={}, required=False, description="Dict"),
            ParamSchema(name="optional_none", type=str, default=None, required=False, description="None default"),
        ]

        func_info = FunctionInfo(
            name="mixed_func",
            func=lambda: None,
            description="Mixed",
            params=params,
            return_type=GenericOutput,
        )

        result = extract_function_params(func_info, {"required_str": "test"})

        expected = {
            "required_str": "test",
            "optional_int": 42,
            "optional_list": [],
            "optional_dict": {},
            # optional_none excluded (None default)
        }
        assert result == expected

    def test_extract_function_params_partial_override(self):
        """Test partial override of defaults."""
        params = [
            ParamSchema(name="p1", type=str, default="d1", required=False, description="P1"),
            ParamSchema(name="p2", type=int, default=10, required=False, description="P2"),
            ParamSchema(name="p3", type=bool, default=True, required=False, description="P3"),
        ]

        func_info = FunctionInfo(
            name="partial_func",
            func=lambda: None,
            description="Partial",
            params=params,
            return_type=GenericOutput,
        )

        result = extract_function_params(func_info, {"p2": 20})
        assert result == {"p1": "d1", "p2": 20, "p3": True}


# ---------------------------------------------------------------------------
# Tests: _execute_function
# ---------------------------------------------------------------------------

class TestExecuteFunctionWithParams:
    """Tests for _execute_function — execution with error handling."""

    def test_execute_function_with_params_success(self, sample_function_info):
        result = execute_function_with_params(sample_function_info, {"x": 5, "y": 3}, "POST")
        assert result["result"] == 8
        assert result["success"] is True
        assert result["message"] is None

    def test_execute_function_with_params_dict_result(self):
        def dict_func(name: str) -> dict:
            return {"greeting": f"Hello, {name}!"}

        func_info = FunctionInfo(
            name="dict_func",
            func=dict_func,
            description="Returns dict",
            params=[ParamSchema(name="name", type=str, required=True, description="Name")],
            return_type=GenericOutput,
        )

        result = execute_function_with_params(func_info, {"name": "World"}, "GET")
        assert result == {"greeting": "Hello, World!"}

    def test_execute_function_with_params_value_error(self):
        def failing_func(x: int) -> int:
            if not isinstance(x, int):
                raise ValueError("x must be an integer")
            return x

        func_info = FunctionInfo(
            name="failing_func",
            func=failing_func,
            description="Failing",
            params=[ParamSchema(name="x", type=int, required=True, description="x")],
            return_type=GenericOutput,
        )

        with pytest.raises(HTTPException) as exc_info:
            execute_function_with_params(func_info, {"x": "not_an_int"}, "POST")

        assert exc_info.value.status_code == 400
        assert "Parameter error" in str(exc_info.value.detail)

    def test_execute_function_with_params_runtime_error(self):
        def error_func(x: int) -> int:
            raise RuntimeError("Something went wrong")

        func_info = FunctionInfo(
            name="error_func",
            func=error_func,
            description="Error",
            params=[ParamSchema(name="x", type=int, required=True, description="x")],
            return_type=GenericOutput,
        )

        with pytest.raises(HTTPException) as exc_info:
            execute_function_with_params(func_info, {"x": 5}, "POST")

        assert exc_info.value.status_code == 500
        assert "Internal error" in str(exc_info.value.detail)

    @patch('refract.api.logger')
    def test_execute_function_with_params_logging(self, mock_logger, sample_function_info):
        execute_function_with_params(sample_function_info, {"x": 5, "y": 3}, "POST")

        assert mock_logger.debug.call_count >= 1
        log_calls = [call[0][0] for call in mock_logger.debug.call_args_list if call[0]]
        request_log = next((log for log in log_calls if "POST test_add" in str(log)), None)
        assert request_log is not None
        assert "params={'x': 5, 'y': 3}" in str(request_log)

    def test_execute_function_with_params_type_error(self):
        """TypeError is caught as a 400."""
        def type_error_func(x: int, y: str) -> str:
            return f"Result: {x + len(y)}"

        func_info = FunctionInfo(
            name="type_error_func",
            func=type_error_func,
            description="Type error func",
            params=[
                ParamSchema(name="x", type=int, required=True, description="x"),
                ParamSchema(name="y", type=str, required=True, description="y"),
            ],
            return_type=GenericOutput,
        )

        with pytest.raises(HTTPException) as exc_info:
            execute_function_with_params(func_info, {"x": "not_int", "y": 123}, "POST")

        assert exc_info.value.status_code == 400

    def test_execute_function_with_params_custom_exception(self):
        """Custom exceptions that aren't ValueError/TypeError become 500."""
        class CustomError(Exception):
            pass

        def custom_error_func(x: int) -> int:
            if x < 0:
                raise CustomError("Negative values not allowed")
            return x * 2

        func_info = FunctionInfo(
            name="custom_error_func",
            func=custom_error_func,
            description="Custom error",
            params=[ParamSchema(name="x", type=int, required=True, description="x")],
            return_type=GenericOutput,
        )

        with pytest.raises(HTTPException) as exc_info:
            execute_function_with_params(func_info, {"x": -5}, "POST")

        assert exc_info.value.status_code == 500
        assert "Internal error" in str(exc_info.value.detail)

    @patch('refract.api.logger')
    def test_execute_function_error_logging(self, mock_logger):
        def error_func() -> str:
            raise ValueError("Test error for logging")

        func_info = FunctionInfo(
            name="error_func",
            func=error_func,
            description="Error func",
            params=[],
            return_type=GenericOutput,
        )

        with pytest.raises(HTTPException):
            execute_function_with_params(func_info, {}, "POST")

        mock_logger.warning.assert_called_once()
        log_call = mock_logger.warning.call_args[0][0]
        assert "POST error_func param error" in log_call
        assert "Test error for logging" in log_call


# ---------------------------------------------------------------------------
# Tests: create_handler
# ---------------------------------------------------------------------------

class TestCreateHandler:
    """Tests for create_handler — endpoint handler creation."""

    def test_create_handler_post(self, sample_function_info):
        handler, model = create_handler(sample_function_info, "POST")

        assert callable(handler)
        assert issubclass(model, BaseModel)
        assert model.__name__ == "Test_AddInput"
        assert asyncio.iscoroutinefunction(handler)

    def test_create_handler_get(self, sample_function_info):
        handler, model = create_handler(sample_function_info, "GET")

        assert callable(handler)
        assert issubclass(model, BaseModel)
        assert model.__name__ == "Test_AddQueryParams"
        assert asyncio.iscoroutinefunction(handler)

    def test_handler_execution_post(self, sample_function_info):
        handler, model = create_handler(sample_function_info, "POST")

        request = model(x=5, y=3)
        result = asyncio.run(handler(request))

        assert result == {"result": 8, "success": True, "message": None}


# ---------------------------------------------------------------------------
# Tests: _add_function_endpoints
# ---------------------------------------------------------------------------

class TestAddFunctionEndpoints:
    """Tests for _add_function_endpoints — parameterized endpoint registration."""

    def test_add_function_endpoints_registers_get_and_post(self):
        func = _make_api_func_info("param_fn", http_methods=["GET", "POST"])
        mock_target = Mock()
        mock_target.add_api_route = Mock()

        _add_function_endpoints(mock_target, [func], lambda name: None)

        assert mock_target.add_api_route.call_count == 2
        methods = [c[1]["methods"][0] for c in mock_target.add_api_route.call_args_list]
        assert "GET" in methods
        assert "POST" in methods

    def test_add_function_endpoints_skips_non_api_interface(self):
        mcp_only = FunctionInfo(
            name="mcp_only",
            func=lambda: None,
            description="MCP only",
            params=[],
            interfaces=["mcp"],
            return_type=GenericOutput,
        )
        mock_target = Mock()
        mock_target.add_api_route = Mock()

        _add_function_endpoints(mock_target, [mcp_only], lambda name: None)

        mock_target.add_api_route.assert_not_called()

    def test_add_function_endpoints_empty_list(self):
        mock_target = Mock()
        mock_target.add_api_route = Mock()

        _add_function_endpoints(mock_target, [], lambda name: None)

        mock_target.add_api_route.assert_not_called()

    def test_add_function_endpoints_streaming_function(self):
        """Streaming function is registered as POST with SSE summary."""
        async def mock_stream(**kw):
            yield "event: complete\ndata: {}\n\n"

        stream_func_info = FunctionInfo(
            name="chat_stream",
            func=Mock(),
            description="Chat streaming",
            params=[ParamSchema(name="message", type=str, required=True, description="msg")],
            http_methods=["POST"],
            interfaces=["api"],
            return_type=GenericOutput,
            streaming=True,
        )

        mock_target = Mock()
        mock_target.add_api_route = Mock()

        _add_function_endpoints(mock_target, [stream_func_info], lambda name: mock_stream)

        assert mock_target.add_api_route.call_count == 1
        call_args = mock_target.add_api_route.call_args
        assert call_args[0][0] == "/chat_stream"
        assert call_args[1]["methods"] == ["POST"]
        assert call_args[1]["operation_id"] == "chat_stream_stream"
        assert "[SSE Stream]" in call_args[1]["summary"]

    def test_add_function_endpoints_streaming_without_stream_func_logs_error(self):
        """Streaming function with no stream_func logs error and skips the route."""
        stream_func_info = FunctionInfo(
            name="broken_stream",
            func=Mock(),
            description="Broken stream",
            params=[],
            http_methods=["POST"],
            interfaces=["api"],
            return_type=GenericOutput,
            streaming=True,
        )

        mock_target = Mock()
        mock_target.add_api_route = Mock()

        with patch('refract.api.logger') as mock_logger:
            _add_function_endpoints(mock_target, [stream_func_info], lambda name: None)

        mock_target.add_api_route.assert_not_called()
        mock_logger.error.assert_called_once()
        assert "broken_stream" in mock_logger.error.call_args[0][0]

    def test_add_function_endpoints_mixed_streaming_and_normal(self):
        """Both streaming and normal functions can coexist."""
        normal_func = FunctionInfo(
            name="normal",
            func=lambda: GenericOutput(result="ok", success=True),
            description="Normal",
            params=[],
            http_methods=["GET"],
            interfaces=["api"],
            return_type=GenericOutput,
            streaming=False,
        )
        stream_func = FunctionInfo(
            name="streamer",
            func=Mock(),
            description="Stream",
            params=[ParamSchema(name="msg", type=str, required=True, description="msg")],
            http_methods=["POST"],
            interfaces=["api"],
            return_type=GenericOutput,
            streaming=True,
        )

        async def mock_stream(**kw):
            yield "event: complete\ndata: {}\n\n"

        mock_target = Mock()
        mock_target.add_api_route = Mock()

        _add_function_endpoints(mock_target, [normal_func, stream_func], lambda name: mock_stream)

        assert mock_target.add_api_route.call_count == 2

    def test_add_function_endpoints_custom_methods(self):
        """Test registering endpoints with custom HTTP methods."""
        custom_func_info = FunctionInfo(
            name="custom_func",
            func=lambda x: GenericOutput(result=x, success=True),
            description="Custom PUT/DELETE",
            params=[ParamSchema(name="x", type=str, required=True, description="Param")],
            http_methods=["PUT", "DELETE"],
            interfaces=["api"],
            return_type=GenericOutput,
        )

        mock_target = Mock()
        mock_target.add_api_route = Mock()

        _add_function_endpoints(mock_target, [custom_func_info], lambda name: None)

        assert mock_target.add_api_route.call_count == 2
        methods = [c[1]["methods"][0] for c in mock_target.add_api_route.call_args_list]
        assert "PUT" in methods
        assert "DELETE" in methods


# ---------------------------------------------------------------------------
# Tests: _register_static_files
# ---------------------------------------------------------------------------

class TestRegisterStaticFiles:
    """Tests for _register_static_files."""

    def test_mounts_elements_if_exists(self):
        """When elements subdir exists, it gets mounted at /elements."""
        with tempfile.TemporaryDirectory() as base_dir:
            # Simulate refract package dir
            refract_pkg_dir = os.path.join(base_dir, "refract")
            os.makedirs(refract_pkg_dir)
            os.makedirs(os.path.join(refract_pkg_dir, "web", "elements"))

            mock_app = Mock()
            with patch('refract.api.os.path.dirname', return_value=refract_pkg_dir):
                _register_static_files(mock_app)

            assert mock_app.mount.call_count == 1
            route = mock_app.mount.call_args[0][0]
            assert route == "/elements"

    def test_not_mounted_when_no_directories_exist(self):
        """When web/elements doesn't exist, app.mount is never called."""
        with tempfile.TemporaryDirectory() as base_dir:
            refract_pkg_dir = os.path.join(base_dir, "refract")
            os.makedirs(refract_pkg_dir)
            # No web/elements created

            mock_app = Mock()
            with patch('refract.api.os.path.dirname', return_value=refract_pkg_dir):
                _register_static_files(mock_app)

            mock_app.mount.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: create_router_for_refract
# ---------------------------------------------------------------------------

class TestCreateRouterForRefract:
    """Tests for create_router_for_refract — router/bring-your-own-app mode."""

    def test_router_returns_apirouter(self):
        from fastapi.routing import APIRouter

        stub = _make_refract_stub()
        router = create_router_for_refract(stub)

        assert isinstance(router, APIRouter)

    def test_router_registers_dynamic_endpoints(self):
        func = _make_api_func_info("add_nums")
        stub = _make_refract_stub(functions=[func])
        router = create_router_for_refract(stub)

        route_paths = [r.path for r in router.routes if hasattr(r, "path")]
        assert "/add_nums" in route_paths

    def test_router_has_functions_details_endpoint(self):
        stub = _make_refract_stub()
        router = create_router_for_refract(stub)

        route_paths = [r.path for r in router.routes if hasattr(r, "path")]
        assert "/functions/details" in route_paths

    def test_router_has_health_endpoint(self):
        stub = _make_refract_stub()
        router = create_router_for_refract(stub)

        route_paths = [r.path for r in router.routes if hasattr(r, "path")]
        assert "/health" in route_paths

    def test_router_excludes_root_html_pages(self):
        stub = _make_refract_stub()
        router = create_router_for_refract(stub)

        route_paths = {r.path for r in router.routes if hasattr(r, "path")}
        for html_path in ["/", "/functions", "/demo", "/tests"]:
            assert html_path not in route_paths

    def test_router_mountable_on_custom_fastapi_app(self):
        func = _make_api_func_info("my_fn")
        stub = _make_refract_stub(functions=[func])
        router = create_router_for_refract(stub)

        custom_app = FastAPI()
        custom_app.include_router(router)
        client = TestClient(custom_app)

        response = client.get("/my_fn?x=3&y=4")
        assert response.status_code == 200
        data = response.json()
        assert data["result"] == 7

    def test_router_health_endpoint_returns_correct_count(self):
        f1 = _make_api_func_info("fn1")
        f2 = _make_api_func_info("fn2")
        stub = _make_refract_stub(functions=[f1, f2])
        router = create_router_for_refract(stub)

        custom_app = FastAPI()
        custom_app.include_router(router)
        client = TestClient(custom_app)

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["functions"] == 2

    def test_router_functions_details_returns_instance_schemas(self):
        func = _make_api_func_info("unique_router_fn")
        stub = _make_refract_stub(functions=[func])
        router = create_router_for_refract(stub)

        custom_app = FastAPI()
        custom_app.include_router(router)
        client = TestClient(custom_app)

        response = client.get("/functions/details")
        assert response.status_code == 200
        data = response.json()
        assert "functions" in data
        assert "unique_router_fn" in data["functions"]

    def test_router_empty_registry_no_dynamic_routes(self):
        stub = _make_refract_stub()
        router = create_router_for_refract(stub)

        route_paths = {r.path for r in router.routes if hasattr(r, "path")}
        assert "/functions/details" in route_paths
        assert "/health" in route_paths
        assert "/add_nums" not in route_paths


# ---------------------------------------------------------------------------
# Tests: create_api_app_for_refract
# ---------------------------------------------------------------------------

class TestCreateApiAppForRefract:
    """Tests for create_api_app_for_refract — full-app mode."""

    def test_api_app_returns_fastapi_instance(self):
        stub = _make_refract_stub()
        app = create_api_app_for_refract(stub)
        assert isinstance(app, FastAPI)

    def test_api_app_title_uses_refract_name(self):
        refract = Refract("my-service")
        app = create_api_app_for_refract(refract)
        assert "my-service" in app.title

    def test_api_app_has_dynamic_endpoints(self):
        func = _make_api_func_info("greet")
        stub = _make_refract_stub(functions=[func])
        app = create_api_app_for_refract(stub)
        client = TestClient(app)

        response = client.get("/greet?x=10")
        assert response.status_code == 200
        data = response.json()
        assert data["result"] == 11

    def test_api_app_has_health_endpoint(self):
        stub = _make_refract_stub()
        app = create_api_app_for_refract(stub)
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_api_app_health_reflects_instance_count(self):
        f1 = _make_api_func_info("fn_a")
        f2 = _make_api_func_info("fn_b")
        stub = _make_refract_stub(functions=[f1, f2])
        app = create_api_app_for_refract(stub)
        client = TestClient(app)

        response = client.get("/health")
        assert response.json()["functions"] == 2

    def test_api_app_has_functions_details_endpoint(self):
        func = _make_api_func_info("my_detail_fn")
        stub = _make_refract_stub(functions=[func])
        app = create_api_app_for_refract(stub)
        client = TestClient(app)

        response = client.get("/functions/details")
        assert response.status_code == 200
        data = response.json()
        assert "my_detail_fn" in data["functions"]

    def test_api_app_has_root_endpoint(self):
        stub = _make_refract_stub()
        app = create_api_app_for_refract(stub)

        root_routes = [r for r in app.routes if hasattr(r, "path") and r.path == "/"]
        assert len(root_routes) == 1

    def test_api_app_has_functions_endpoint(self):
        stub = _make_refract_stub()
        app = create_api_app_for_refract(stub)

        routes = [r for r in app.routes if hasattr(r, "path") and r.path == "/functions"]
        assert len(routes) == 1

    def test_api_app_isolated_from_global_registry(self):
        """Refract.api() uses instance registry, not the global registry."""
        from refract.registry import register_function

        @register_function()
        def global_only_fn(z: int) -> GenericOutput:
            """Global only."""
            return GenericOutput(result=z)

        instance_func = _make_api_func_info("instance_only_fn")
        refract = Refract("isolated")
        refract._registry.append(instance_func)

        app = create_api_app_for_refract(refract)
        client = TestClient(app)

        resp = client.get("/instance_only_fn?x=5")
        assert resp.status_code == 200

        resp = client.get("/global_only_fn?z=1")
        assert resp.status_code == 404

    def test_api_app_full_integration(self):
        """Full integration: POST to a registered function."""
        func = _make_api_func_info("calc", http_methods=["GET", "POST"])
        stub = _make_refract_stub(functions=[func])
        app = create_api_app_for_refract(stub)
        client = TestClient(app)

        response = client.get("/calc?x=5&y=3")
        assert response.status_code == 200
        assert response.json()["result"] == 8

        response = client.post("/calc", json={"x": 10, "y": 5})
        assert response.status_code == 200
        assert response.json()["result"] == 15

    def test_api_app_missing_required_param_422(self):
        """Missing required param returns 422 (FastAPI validation)."""
        func = _make_api_func_info("validate_fn")
        stub = _make_refract_stub(functions=[func])
        app = create_api_app_for_refract(stub)
        client = TestClient(app)

        response = client.get("/validate_fn")  # Missing x
        assert response.status_code == 422
