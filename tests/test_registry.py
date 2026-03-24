"""
Tests for refract.registry module.

Tests the central registry system that enables automatic generation of CLI commands,
API endpoints, and MCP tools through function registration and parameter inference.
"""
import pytest
import inspect
from typing import Any
from unittest.mock import patch, Mock

from refract.registry import (
    _generate_function_info, register_function,
    _clear_pending,
    RegistryError, _has_register_decorator,
    _pending_registrations, _pending_stream_funcs,
)
from refract import Refract
from pydantic import BaseModel
from refract.models import FunctionInfo, ParamSchema, GenericOutput, FunctionSchema


class TestGenerateFunctionInfo:
    """Tests for _generate_function_info - automatic parameter inference."""

    def test_generate_function_info_simple(self):
        """Test function info generation from simple function."""
        def simple_func(x: int, y: str = "default") -> GenericOutput:
            """Simple function for testing.

            Args:
                x: An integer parameter
                y: A string parameter with default

            Returns:
                A formatted string
            """
            return GenericOutput(result=f"{x}: {y}", success=True)

        info = _generate_function_info(simple_func)

        assert info.name == "simple_func"
        assert info.func == simple_func
        assert info.description == "Simple function for testing."
        assert info.http_methods == ["GET", "POST"]  # Default
        assert len(info.params) == 2

        x_param = info.params[0]
        assert x_param.name == "x"
        assert x_param.type == int
        assert x_param.required is True
        assert x_param.default is None
        assert x_param.description == "An integer parameter"

        y_param = info.params[1]
        assert y_param.name == "y"
        assert y_param.type == str
        assert y_param.required is False
        assert y_param.default == "default"
        assert y_param.description == "A string parameter with default"

    def test_generate_function_info_no_annotations(self):
        """Test function info generation without type annotations - should fail without return type."""
        def no_annotations_func(x, y=42):
            """Function without type annotations."""
            return x + y

        with pytest.raises(RegistryError, match="must have a return type annotation of BaseModel"):
            _generate_function_info(no_annotations_func)

    def test_generate_function_info_with_any_params(self):
        """Test function info generation with Any type parameters but GenericOutput return."""
        def any_params_func(x, y=42) -> GenericOutput:
            """Function with Any type parameters."""
            return GenericOutput(result=x + y, success=True)

        info = _generate_function_info(any_params_func)

        assert info.name == "any_params_func"
        assert len(info.params) == 2

        x_param = info.params[0]
        assert x_param.name == "x"
        assert x_param.type == Any
        assert x_param.required is True

        y_param = info.params[1]
        assert y_param.name == "y"
        assert y_param.type == Any
        assert y_param.required is False
        assert y_param.default == 42

    def test_generate_function_info_no_docstring(self):
        """Test function info generation without docstring."""
        def no_doc_func(x: int) -> GenericOutput:
            return GenericOutput(result=x * 2, success=True)

        info = _generate_function_info(no_doc_func)

        assert info.name == "no_doc_func"
        assert info.description == "Execute no_doc_func"  # Default description
        assert len(info.params) == 1

        param = info.params[0]
        assert param.description == "Parameter x"

    def test_generate_function_info_custom_http_methods(self):
        """Test function info generation with custom HTTP methods."""
        def custom_func(x: int) -> GenericOutput:
            """Custom function."""
            return GenericOutput(result=x, success=True)

        info = _generate_function_info(custom_func, http_methods=["POST", "PUT"])

        assert info.http_methods == ["POST", "PUT"]

    def test_generate_function_info_invalid_http_methods(self):
        """Test function info generation with invalid HTTP methods."""
        def test_func(x: int) -> GenericOutput:
            return GenericOutput(result=x, success=True)

        with pytest.raises(ValueError, match="Invalid HTTP methods"):
            _generate_function_info(test_func, http_methods=["INVALID"])

    def test_generate_function_info_complex_signature(self):
        """Test function info generation with complex signature."""
        def complex_func(
            required_param: str,
            optional_param: int = 10,
            *args,
            **kwargs
        ) -> GenericOutput:
            """Complex function with various parameter types.

            Args:
                required_param: A required string parameter
                optional_param: An optional integer parameter
            """
            return GenericOutput(result={"result": "complex"}, success=True)

        info = _generate_function_info(complex_func)

        assert len(info.params) == 2

        required = info.params[0]
        assert required.name == "required_param"
        assert required.type == str
        assert required.required is True

        optional = info.params[1]
        assert optional.name == "optional_param"
        assert optional.type == int
        assert optional.required is False
        assert optional.default == 10


class TestRegisterFunctionDecorator:
    """Tests for register_function decorator."""

    def test_register_function_basic(self):
        """Test basic function registration."""
        @register_function()
        def test_basic_func(x: int) -> GenericOutput:
            """Basic test function."""
            return GenericOutput(result=x * 2, success=True)

        app = Refract("test")
        func_info = app.get_function_by_name("test_basic_func")
        assert func_info is not None

        assert func_info.name == "test_basic_func"
        assert func_info.func == test_basic_func
        assert func_info.description == "Basic test function."
        assert len(func_info.params) == 1
        assert func_info.params[0].name == "x"

        result = test_basic_func(5)
        assert result.result == 10

    def test_register_function_custom_methods(self):
        """Test function registration with custom HTTP methods."""
        @register_function(http_methods=["GET"])
        def get_only_func(x: str) -> GenericOutput:
            """GET-only function."""
            return GenericOutput(result=f"GET: {x}", success=True)

        app = Refract("test")
        func_info = app.get_function_by_name("get_only_func")
        assert func_info is not None
        assert func_info.http_methods == ["GET"]

    def test_register_function_error_handling(self):
        """Test error handling in function registration."""
        with patch('refract.registry._generate_function_info') as mock_generate:
            mock_generate.side_effect = Exception("Generation error")

            with pytest.raises(RegistryError, match="Failed to register function"):
                @register_function()
                def failing_func():
                    pass

    def test_register_function_duplicate_raises_error(self):
        """Test that registering a function with the same name raises RegistryError."""
        @register_function()
        def duplicate_test_func(x: int) -> GenericOutput:
            """First registration."""
            return GenericOutput(result=x, success=True)

        with pytest.raises(RegistryError, match="already registered"):
            @register_function()
            def duplicate_test_func(y: str) -> GenericOutput:  # noqa: F811
                """Second registration with same name."""
                return GenericOutput(result=y, success=True)


class TestRegistryIntegration:
    """Integration tests for registry functionality."""

    def test_end_to_end_function_registration_and_usage(self):
        """Test complete flow from registration to usage."""
        @register_function(http_methods=["GET", "POST"])
        def integration_test_func(name: str, count: int = 1) -> GenericOutput:
            """Integration test function.

            Args:
                name: The name to repeat
                count: How many times to repeat it
            """
            return GenericOutput(result=" ".join([name] * count), success=True)

        app = Refract("test")
        func_info = app.get_function_by_name("integration_test_func")
        assert func_info is not None

        result = func_info.func("test", 3)
        assert result.result == "test test test"

        schemas = app.get_all_schemas()
        schema = next((s for s in schemas if s.name == "integration_test_func"), None)
        assert schema is not None
        params = schema.parameters
        assert len(params) == 2

        name_param = next(p for p in params if p.name == "name")
        count_param = next(p for p in params if p.name == "count")

        assert name_param.required is True
        assert count_param.required is False
        assert count_param.default == 1

        assert "GET" in func_info.http_methods
        assert "POST" in func_info.http_methods

    def test_registry_access_nonexistent_function(self):
        """Test that searching for non-existent function returns None."""
        app = Refract("test")
        result = app.get_function_by_name("does_not_exist")
        assert result is None


class TestDecoratorDetection:
    """Tests for @register_function decorator detection in source files using AST."""

    def test_has_register_decorator_true(self, tmp_path):
        """Test detection of @register_function() in source file."""
        module_file = tmp_path / "test_module.py"
        module_file.write_text('''
from refract import register_function, GenericOutput

@register_function()
def my_func() -> GenericOutput:
    return GenericOutput(result="test", success=True)
''')

        assert _has_register_decorator(str(module_file)) is True

    def test_has_register_decorator_without_parens(self, tmp_path):
        """Test detection of @register_function without parentheses."""
        module_file = tmp_path / "test_module_no_parens.py"
        module_file.write_text('''
from refract import register_function, GenericOutput

@register_function
def my_func() -> GenericOutput:
    return GenericOutput(result="test", success=True)
''')

        assert _has_register_decorator(str(module_file)) is True

    def test_has_register_decorator_with_module_prefix(self, tmp_path):
        """Test detection of @registry.register_function() with module prefix."""
        module_file = tmp_path / "test_module_prefix.py"
        module_file.write_text('''
from refract import registry
from refract.models import GenericOutput

@registry.register_function()
def my_func() -> GenericOutput:
    return GenericOutput(result="test", success=True)
''')

        assert _has_register_decorator(str(module_file)) is True

    def test_has_register_decorator_false(self, tmp_path):
        """Test that modules without decorator are correctly identified."""
        module_file = tmp_path / "utility_module.py"
        module_file.write_text('''
def helper_function(x, y):
    """A utility function without registration."""
    return x + y

class UtilityClass:
    pass
''')

        assert _has_register_decorator(str(module_file)) is False

    def test_has_register_decorator_in_comment_false(self, tmp_path):
        """Test that @register_function in comments is NOT detected (AST ignores comments)."""
        module_file = tmp_path / "module_with_comment.py"
        module_file.write_text('''
# This file uses @register_function decorator for functions
# @register_function should be used like this:

def helper_function(x, y):
    """
    Example with @register_function decorator.
    """
    return x + y
''')

        assert _has_register_decorator(str(module_file)) is False

    def test_has_register_decorator_in_docstring_false(self, tmp_path):
        """Test that @register_function in docstrings is NOT detected (AST accuracy)."""
        module_file = tmp_path / "module_with_docstring.py"
        module_file.write_text('''
def helper_function(x, y):
    """
    This function shows how to use @register_function decorator.
    Use @register_function() to register functions in the registry.
    """
    return x + y
''')

        assert _has_register_decorator(str(module_file)) is False

    def test_has_register_decorator_invalid_path(self):
        """Test handling of invalid/non-existent file paths."""
        assert _has_register_decorator("/nonexistent/path/module.py") is False
        assert _has_register_decorator(None) is False
        assert _has_register_decorator("") is False

    def test_has_register_decorator_invalid_syntax(self, tmp_path):
        """Test handling of files with invalid Python syntax."""
        module_file = tmp_path / "invalid_syntax.py"
        module_file.write_text('''
def broken_function(
    # Missing closing parenthesis
''')

        assert _has_register_decorator(str(module_file)) is False


class TestRegisterStreamingFunction:
    """Tests for streaming support in register_function."""

    def test_register_streaming_function(self):
        """streaming=True propagates to FunctionInfo and stream_func is stored."""
        async def mock_stream(**kwargs):
            yield "chunk"

        @register_function(streaming=True, stream_func=mock_stream)
        def streaming_func(message: str) -> GenericOutput:
            """A streaming function."""
            return GenericOutput(result=message, success=True)

        app = Refract("test")
        func_info = app.get_function_by_name("streaming_func")
        assert func_info is not None
        assert func_info.streaming is True

        retrieved = app.get_stream_func("streaming_func")
        assert retrieved is mock_stream

    def test_register_non_streaming_default(self):
        """Normal registration keeps streaming=False, no stream_func."""
        @register_function()
        def normal_func(x: int) -> GenericOutput:
            """A normal function."""
            return GenericOutput(result=x, success=True)

        app = Refract("test")
        func_info = app.get_function_by_name("normal_func")
        assert func_info is not None
        assert func_info.streaming is False

        assert app.get_stream_func("normal_func") is None

    def test_register_streaming_without_stream_func_raises(self):
        """streaming=True without stream_func raises RegistryError."""
        with pytest.raises(RegistryError, match="streaming=True requires stream_func"):
            @register_function(streaming=True)
            def bad_streaming_func(message: str) -> GenericOutput:
                """Bad streaming function."""
                return GenericOutput(result=message, success=True)

    def test_clear_pending_clears_stream_funcs(self):
        """_clear_pending() also clears _pending_stream_funcs."""
        async def mock_stream(**kwargs):
            yield "chunk"

        @register_function(streaming=True, stream_func=mock_stream)
        def stream_func_clear_test(message: str) -> GenericOutput:
            """A streaming function."""
            return GenericOutput(result=message, success=True)

        assert len(_pending_stream_funcs) > 0
        assert len(_pending_registrations) > 0

        _clear_pending()

        assert len(_pending_registrations) == 0
        assert len(_pending_stream_funcs) == 0


class TestBaseModelSupport:
    """Tests for relaxed return type validation: any BaseModel subclass is accepted."""

    def test_register_function_accepts_plain_basemodel(self):
        """Functions returning a plain BaseModel subclass (not GenericOutput) can be registered."""
        class SearchResponse(BaseModel):
            users: list[str]
            total: int

        @register_function()
        def search_users(query: str) -> SearchResponse:
            """Search for users.

            Args:
                query: Search query
            """
            return SearchResponse(users=["ana"], total=1)

        app = Refract("test")
        func_info = app.get_function_by_name("search_users")
        assert func_info is not None
        assert func_info.name == "search_users"
        assert func_info.return_type is SearchResponse

        result = search_users("test")
        assert result.users == ["ana"]
        assert result.total == 1

    def test_register_function_generic_output_still_works(self):
        """GenericOutput (a BaseModel subclass) continues to register correctly."""
        @register_function()
        def legacy_func(x: int) -> GenericOutput:
            """Legacy function using GenericOutput."""
            return GenericOutput(result=x, success=True)

        app = Refract("test")
        func_info = app.get_function_by_name("legacy_func")
        assert func_info is not None
        assert func_info.return_type is GenericOutput

    def test_register_function_rejects_non_basemodel_return(self):
        """Functions returning a non-BaseModel type (e.g. str, int) still raise RegistryError."""
        with pytest.raises(RegistryError, match="must return BaseModel"):
            @register_function()
            def bad_func(x: int) -> str:
                """Bad function with str return type."""
                return str(x)

    def test_register_function_rejects_dict_return(self):
        """Functions returning dict (not a BaseModel) raise RegistryError."""
        with pytest.raises(RegistryError, match="must return BaseModel"):
            @register_function()
            def dict_func(x: int) -> dict:
                """Function returning raw dict."""
                return {"x": x}

    def test_generate_function_info_accepts_basemodel_subclass(self):
        """_generate_function_info accepts any BaseModel subclass as return type."""
        class RichResponse(BaseModel):
            items: list[str]
            count: int
            page: int = 1

        def rich_func(query: str) -> RichResponse:
            """Rich function.

            Args:
                query: Query string
            """
            return RichResponse(items=[], count=0)

        info = _generate_function_info(rich_func)

        assert info.name == "rich_func"
        assert info.return_type is RichResponse

    def test_basemodel_subclass_return_type_stored_in_function_info(self):
        """return_type in FunctionInfo is set to the actual BaseModel subclass."""
        class TypedResponse(BaseModel):
            value: int
            label: str

        @register_function(http_methods=["GET"])
        def typed_func(x: int) -> TypedResponse:
            """Typed function."""
            return TypedResponse(value=x, label="ok")

        app = Refract("test")
        func_info = app.get_function_by_name("typed_func")
        assert func_info is not None
        assert func_info.return_type is TypedResponse
        assert issubclass(func_info.return_type, BaseModel)


class TestRefractClass:
    """Tests for the Refract instance-based registry class."""

    def test_refract_instantiation_empty(self):
        """Refract can be instantiated without discover, resulting in an empty registry."""
        app = Refract("test-project")

        assert app.name == "test-project"
        assert app.function_count() == 0
        assert app.get_all_functions() == []

    def test_refract_repr(self):
        """Refract has a meaningful repr."""
        app = Refract("my-app")
        assert "my-app" in repr(app)
        assert "0" in repr(app)

    def test_refract_collects_pending_registrations(self):
        """Refract() auto-drains _pending_registrations on instantiation."""
        def my_func(x: int) -> GenericOutput:
            """My function."""
            return GenericOutput(result=x)

        info = FunctionInfo(
            name="refract_test_func",
            func=my_func,
            description="My function.",
            params=[],
            return_type=GenericOutput,
        )
        _pending_registrations.append(info)

        app = Refract("collector")  # auto-drains on __init__

        assert app.function_count() == 1
        assert app.get_function_by_name("refract_test_func") is not None
        # Pending buffer is now empty
        assert len(_pending_registrations) == 0

    def test_refract_instance_isolation(self):
        """Two Refract instances do not share state."""
        app1 = Refract("app1")
        app2 = Refract("app2")

        def func_a(x: int) -> GenericOutput:
            """Func A."""
            return GenericOutput(result=x)

        info_a = FunctionInfo(
            name="func_a", func=func_a, description="Func A.", params=[], return_type=GenericOutput
        )
        app1._registry.append(info_a)

        assert app1.function_count() == 1
        assert app2.function_count() == 0
        assert app1.get_function_by_name("func_a") is not None
        assert app2.get_function_by_name("func_a") is None

    def test_refract_clear(self):
        """Refract.clear() empties the instance registry."""
        app = Refract("clearable")

        def fn(x: int) -> GenericOutput:
            """Fn."""
            return GenericOutput(result=x)

        instance_info = FunctionInfo(
            name="instance_func",
            func=fn,
            description="Instance function.",
            params=[],
            return_type=GenericOutput,
        )
        app._registry.append(instance_info)
        assert app.function_count() == 1

        app.clear()

        assert app.function_count() == 0

    def test_refract_get_stream_func(self):
        """Refract.get_stream_func returns streaming callables stored during discover."""
        async def my_stream(**kwargs):
            yield "data"

        app = Refract("streamer")

        def streaming_fn(msg: str) -> GenericOutput:
            """Streaming fn."""
            return GenericOutput(result=msg)

        info = FunctionInfo(
            name="my_stream_fn",
            func=streaming_fn,
            description="Streaming fn.",
            params=[],
            return_type=GenericOutput,
            streaming=True,
        )
        app._registry.append(info)
        app._stream_registry["my_stream_fn"] = my_stream

        assert app.get_stream_func("my_stream_fn") is my_stream
        assert app.get_stream_func("nonexistent") is None

    def test_refract_get_functions_for_interface(self):
        """get_functions_for_interface filters correctly."""
        app = Refract("filter-test")

        def fn_api_only(x: int) -> GenericOutput:
            return GenericOutput(result=x)

        def fn_mcp_only(x: int) -> GenericOutput:
            return GenericOutput(result=x)

        info_api = FunctionInfo(
            name="fn_api_only", func=fn_api_only, description="API only.",
            params=[], return_type=GenericOutput, interfaces=["api"],
        )
        info_mcp = FunctionInfo(
            name="fn_mcp_only", func=fn_mcp_only, description="MCP only.",
            params=[], return_type=GenericOutput, interfaces=["mcp"],
        )
        app._registry.extend([info_api, info_mcp])

        api_funcs = app.get_functions_for_interface("api")
        mcp_funcs = app.get_functions_for_interface("mcp")

        assert len(api_funcs) == 1 and api_funcs[0].name == "fn_api_only"
        assert len(mcp_funcs) == 1 and mcp_funcs[0].name == "fn_mcp_only"

    def test_refract_discover_strict_mode_raises_on_bad_package(self):
        """_discover raises RegistryError when a package cannot be imported."""
        app = Refract("strict-test")

        with pytest.raises(RegistryError, match="Failed to import package"):
            app._discover(["nonexistent.package.that.does.not.exist"], strict=False)

    def test_refract_clear_pending_clears_buffer(self):
        """_clear_pending() clears _pending_registrations and _pending_stream_funcs."""
        @register_function()
        def pending_test_func(x: int) -> GenericOutput:
            """Pending test function."""
            return GenericOutput(result=x)

        assert len(_pending_registrations) > 0

        _clear_pending()

        assert len(_pending_registrations) == 0
        assert len(_pending_stream_funcs) == 0

    def test_refract_auto_drains_decorator_registrations(self):
        """@register_function() + Refract() without discover works end-to-end."""
        @register_function()
        def auto_drain_func(x: int) -> GenericOutput:
            """Auto drain function."""
            return GenericOutput(result=x)

        app = Refract("auto")  # drains pending automatically

        assert app.function_count() == 1
        assert app.get_function_by_name("auto_drain_func") is not None

    def test_refract_get_all_schemas(self):
        """get_all_schemas returns serializable FunctionSchema objects."""
        app = Refract("schema-test")

        def fn(x: int) -> GenericOutput:
            """Test fn."""
            return GenericOutput(result=x)

        info = FunctionInfo(
            name="schema_fn", func=fn, description="Test fn.",
            params=[ParamSchema(name="x", type=int, required=True, description="x")],
            return_type=GenericOutput,
        )
        app._registry.append(info)

        schemas = app.get_all_schemas()
        assert len(schemas) == 1
        assert isinstance(schemas[0], FunctionSchema)
        assert schemas[0].name == "schema_fn"
        assert schemas[0].response_schema is not None

    def test_two_refract_instances_dont_share_pending(self):
        """Each Refract() call drains the buffer; a second Refract() gets an empty slate."""
        @register_function()
        def shared_func(x: int) -> GenericOutput:
            """Shared func."""
            return GenericOutput(result=x)

        app1 = Refract("first")   # drains shared_func
        app2 = Refract("second")  # pending is now empty

        assert app1.function_count() == 1
        assert app2.function_count() == 0
