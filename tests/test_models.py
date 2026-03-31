"""
Tests for refract.models module.

Tests the Pydantic models that define input/output contracts for functions
registered in the registry, ensuring data validation and type safety.
"""
import pytest
from typing import Any, Dict, List, Literal, Optional, Tuple, Union
from pydantic import BaseModel, ValidationError

from refract.models import (
    ParamSchema, FunctionInfo, FunctionSchema
)
from tests.conftest import TestOutput


class TestParamSchema:
    """Tests for ParamSchema model - parameter definitions for registry functions."""

    def test_explicit_param_creation_required(self):
        """Test creating required parameter without default."""
        param = ParamSchema(
            name="test_param",
            type=int,
            required=True,
            description="A test parameter"
        )

        assert param.name == "test_param"
        assert param.type == int
        assert param.default is None
        assert param.required is True
        assert param.description == "A test parameter"

    def test_explicit_param_creation_optional(self):
        """Test creating optional parameter with default value."""
        param = ParamSchema(
            name="optional_param",
            type=str,
            default="default_value",
            required=False,
            description="An optional parameter"
        )

        assert param.name == "optional_param"
        assert param.type == str
        assert param.default == "default_value"
        assert param.required is False
        assert param.description == "An optional parameter"

    @pytest.mark.parametrize("param_type", [int, str, float, bool, list, dict, Any])
    def test_explicit_param_supports_various_types(self, param_type):
        """Test that ParamSchema supports various Python types."""
        param = ParamSchema(
            name="test",
            type=param_type,
            required=True,
            description="Test param"
        )

        assert param.type == param_type

    def test_explicit_param_validation_required_fields(self):
        """Test that required fields are validated."""
        with pytest.raises(ValidationError):
            ParamSchema()  # Missing required fields

        with pytest.raises(ValidationError):
            ParamSchema(name="test")  # Missing other required fields


class TestFunctionInfo:
    """Tests for FunctionInfo model - complete function metadata for registry."""

    def test_function_info_creation_minimal(self, sample_function):
        """Test creating FunctionInfo with minimal required fields."""
        func_info = FunctionInfo(
            name="test_func",
            func=sample_function,
            description="Test function",
            params=[],
            return_type=TestOutput
        )

        assert func_info.name == "test_func"
        assert func_info.func == sample_function
        assert func_info.description == "Test function"
        assert func_info.params == []  # Default empty list
        assert func_info.http_methods == ["GET", "POST"]  # Default methods

    def test_function_info_creation_complete(self, sample_function):
        """Test creating FunctionInfo with all fields specified."""
        params = [
            ParamSchema(name="x", type=int, required=True, description="First param"),
            ParamSchema(name="y", type=str, default="test", required=False, description="Second param")
        ]

        func_info = FunctionInfo(
            name="complete_func",
            func=sample_function,
            description="Complete test function",
            params=params,
            http_methods=["GET", "POST", "PUT"],
            return_type=TestOutput
        )

        assert func_info.name == "complete_func"
        assert func_info.func == sample_function
        assert func_info.description == "Complete test function"
        assert len(func_info.params) == 2
        assert func_info.params[0].name == "x"
        assert func_info.params[1].name == "y"
        assert func_info.http_methods == ["GET", "POST", "PUT"]

    def test_function_info_callable_validation(self):
        """Test that FunctionInfo validates callable functions."""
        func_info = FunctionInfo(
            name="test",
            func=lambda x: x,
            description="Test",
            params=[],
            return_type=TestOutput
        )
        assert callable(func_info.func)

        def test_func():
            return "test"

        func_info = FunctionInfo(
            name="test",
            func=test_func,
            description="Test",
            params=[],
            return_type=TestOutput
        )
        assert callable(func_info.func)

    def test_function_info_validation_required_fields(self):
        """Test that required fields are validated."""
        with pytest.raises(ValidationError):
            FunctionInfo()  # Missing all required fields

        with pytest.raises(ValidationError):
            FunctionInfo(name="test")  # Missing func and description


class TestModelsIntegration:
    """Integration tests for models working together."""

    def test_function_info_with_explicit_params(self, sample_function):
        """Test FunctionInfo containing ParamSchema instances."""
        params = [
            ParamSchema(name="x", type=int, required=True, description="First"),
            ParamSchema(name="y", type=str, default="default", required=False, description="Second")
        ]

        func_info = FunctionInfo(
            name="integrated_test",
            func=sample_function,
            description="Integrated test",
            params=params,
            return_type=TestOutput
        )

        assert len(func_info.params) == 2
        assert all(isinstance(p, ParamSchema) for p in func_info.params)

        x_param = func_info.params[0]
        y_param = func_info.params[1]

        assert x_param.name == "x" and x_param.required is True
        assert y_param.name == "y" and y_param.required is False and y_param.default == "default"


class TestFunctionInfoStreaming:
    """Tests for streaming field in FunctionInfo."""

    def test_function_info_streaming_default_false(self, sample_function):
        """streaming field defaults to False."""
        func_info = FunctionInfo(
            name="test_func",
            func=sample_function,
            description="Test function",
            params=[],
            return_type=TestOutput
        )
        assert func_info.streaming is False

    def test_function_info_streaming_true(self, sample_function):
        """streaming can be set to True."""
        func_info = FunctionInfo(
            name="test_func",
            func=sample_function,
            description="Test function",
            params=[],
            return_type=TestOutput,
            streaming=True
        )
        assert func_info.streaming is True

    def test_function_info_to_schema_includes_streaming(self, sample_function):
        """to_schema() includes streaming field when True."""
        func_info = FunctionInfo(
            name="test_func",
            func=sample_function,
            description="Test function",
            params=[],
            return_type=TestOutput,
            streaming=True
        )
        schema = func_info.to_schema()
        assert schema.streaming is True

    def test_function_info_to_schema_streaming_default(self, sample_function):
        """to_schema() streaming defaults to False."""
        func_info = FunctionInfo(
            name="test_func",
            func=sample_function,
            description="Test function",
            params=[],
            return_type=TestOutput
        )
        schema = func_info.to_schema()
        assert schema.streaming is False


class TestFunctionSchemaStreaming:
    """Tests for streaming field in FunctionSchema."""

    def test_function_schema_streaming_default_false(self):
        """streaming field defaults to False."""
        schema = FunctionSchema(
            name="test",
            description="Test",
            http_methods=["GET"],
            parameters=[]
        )
        assert schema.streaming is False

    def test_function_schema_streaming_serialization(self):
        """streaming field is included in serialized output."""
        schema = FunctionSchema(
            name="test",
            description="Test",
            http_methods=["GET"],
            parameters=[],
            streaming=True
        )
        data = schema.model_dump()
        assert data["streaming"] is True


class TestSerializeType:
    """Tests for _serialize_type() - serialization of Python types to strings."""

    def _serialize(self, py_type: Any) -> str:
        """Helper to test _serialize_type() through ParamSchema."""
        param = ParamSchema(
            name="test",
            type=py_type,
            required=True,
            description="Test parameter"
        )
        return param._serialize_type(py_type)

    @pytest.mark.parametrize("py_type,expected", [
        (int, "int"),
        (str, "str"),
        (float, "float"),
        (bool, "bool"),
        (list, "list"),
        (dict, "dict"),
    ])
    def test_basic_types(self, py_type, expected):
        """Verifies that basic types serialize correctly."""
        assert self._serialize(py_type) == expected

    @pytest.mark.parametrize("py_type,expected", [
        (List[str], "list[str]"),
        (List[int], "list[int]"),
        (List[float], "list[float]"),
        (List[bool], "list[bool]"),
        (Dict[str, int], "dict[str, int]"),
        (Dict[str, str], "dict[str, str]"),
        (Dict[str, Any], "dict[str, Any]"),
        (Tuple[int, str], "tuple[int, str]"),
        (Tuple[int, int, int], "tuple[int, int, int]"),
    ])
    def test_generic_types(self, py_type, expected):
        """Verifies that generic types serialize correctly."""
        assert self._serialize(py_type) == expected

    @pytest.mark.parametrize("py_type,expected", [
        (Optional[str], "str?"),
        (Optional[int], "int?"),
        (Optional[float], "float?"),
        (Optional[List[str]], "list[str]?"),
    ])
    def test_optional_types(self, py_type, expected):
        """Verifies that Optional[X] serializes as 'X?'."""
        assert self._serialize(py_type) == expected

    @pytest.mark.parametrize("py_type,expected", [
        (Union[str, int], "str | int"),
        (Union[str, int, float], "str | int | float"),
        (Union[List[str], Dict[str, int]], "list[str] | dict[str, int]"),
    ])
    def test_union_types(self, py_type, expected):
        """Verifies that Union[X, Y] serializes as 'X | Y'."""
        assert self._serialize(py_type) == expected

    def test_literal_strings(self):
        """Verifies that Literal with strings serializes correctly."""
        assert self._serialize(Literal["a", "b"]) == "Literal['a', 'b']"

    def test_literal_ints(self):
        """Verifies that Literal with ints serializes correctly."""
        assert self._serialize(Literal[1, 2, 3]) == "Literal[1, 2, 3]"

    def test_literal_mixed(self):
        """Verifies that mixed Literal serializes correctly."""
        assert self._serialize(Literal["a", 1]) == "Literal['a', 1]"

    @pytest.mark.parametrize("py_type,expected", [
        (List[List[int]], "list[list[int]]"),
        (List[List[List[str]]], "list[list[list[str]]]"),
        (Dict[str, List[int]], "dict[str, list[int]]"),
        (Dict[str, Dict[str, int]], "dict[str, dict[str, int]]"),
        (List[Dict[str, int]], "list[dict[str, int]]"),
        (List[Optional[str]], "list[str?]"),
        (Dict[str, Optional[int]], "dict[str, int?]"),
    ])
    def test_nested_generic_types(self, py_type, expected):
        """Verifies that nested generic types serialize correctly."""
        assert self._serialize(py_type) == expected

    def test_to_schema_with_generic_type(self):
        """Verifies that type_str serializes correctly."""
        param = ParamSchema(
            name="items",
            type=List[str],
            required=True,
            description="List of items"
        )
        assert param.type_str == "list[str]"
        assert param.name == "items"
        assert param.model_dump()['type'] == "list[str]"

    def test_to_schema_with_optional_type(self):
        """Verifies that type_str serializes Optional correctly."""
        param = ParamSchema(
            name="name",
            type=Optional[str],
            required=False,
            default=None,
            description="Optional name"
        )
        assert param.type_str == "str?"
        assert param.model_dump()['type'] == "str?"


class TestFunctionInfoTags:
    """Tests for tags field in FunctionInfo."""

    def test_function_info_tags_default_empty(self, sample_function):
        """tags field defaults to empty list."""
        func_info = FunctionInfo(
            name="test_func",
            func=sample_function,
            description="Test function",
            params=[],
            return_type=TestOutput,
        )
        assert func_info.tags == []

    def test_function_info_tags_can_be_set(self, sample_function):
        """tags can be set to a list of strings."""
        func_info = FunctionInfo(
            name="test_func",
            func=sample_function,
            description="Test function",
            params=[],
            return_type=TestOutput,
            tags=["generators", "image"],
        )
        assert func_info.tags == ["generators", "image"]

    def test_function_info_to_schema_includes_tags(self, sample_function):
        """to_schema() propagates tags to FunctionSchema."""
        func_info = FunctionInfo(
            name="test_func",
            func=sample_function,
            description="Test function",
            params=[],
            return_type=TestOutput,
            tags=["generators", "image"],
        )
        schema = func_info.to_schema()
        assert schema.tags == ["generators", "image"]

    def test_function_info_to_schema_tags_default_empty(self, sample_function):
        """to_schema() tags defaults to empty list when not set."""
        func_info = FunctionInfo(
            name="test_func",
            func=sample_function,
            description="Test function",
            params=[],
            return_type=TestOutput,
        )
        schema = func_info.to_schema()
        assert schema.tags == []


class TestFunctionSchemaTags:
    """Tests for tags field in FunctionSchema."""

    def test_function_schema_tags_default_empty(self):
        """tags field defaults to empty list."""
        schema = FunctionSchema(
            name="test",
            description="Test",
            http_methods=["GET"],
            parameters=[],
        )
        assert schema.tags == []

    def test_function_schema_tags_can_be_set(self):
        """tags accepts a list of strings."""
        schema = FunctionSchema(
            name="test",
            description="Test",
            http_methods=["GET"],
            parameters=[],
            tags=["generators", "audio"],
        )
        assert schema.tags == ["generators", "audio"]

    def test_function_schema_tags_in_serialization(self):
        """tags are included in model_dump() output."""
        schema = FunctionSchema(
            name="test",
            description="Test",
            http_methods=["GET"],
            parameters=[],
            tags=["generators", "image"],
        )
        data = schema.model_dump()
        assert "tags" in data
        assert data["tags"] == ["generators", "image"]

    def test_function_schema_tags_empty_in_serialization(self):
        """tags=[] is serialized as an empty list, not absent."""
        schema = FunctionSchema(
            name="test",
            description="Test",
            http_methods=["GET"],
            parameters=[],
        )
        data = schema.model_dump()
        assert "tags" in data
        assert data["tags"] == []


class TestResponseSchema:
    """Tests for response_schema field in FunctionSchema and FunctionInfo.to_schema()."""

    def test_function_schema_response_schema_default_none(self):
        """response_schema defaults to None when not provided."""
        schema = FunctionSchema(
            name="test",
            description="Test",
            http_methods=["GET"],
            parameters=[]
        )
        assert schema.response_schema is None

    def test_function_schema_response_schema_can_be_set(self):
        """response_schema accepts a dict when provided."""
        json_schema = {"type": "object", "properties": {"result": {"type": "string"}}}
        schema = FunctionSchema(
            name="test",
            description="Test",
            http_methods=["GET"],
            parameters=[],
            response_schema=json_schema
        )
        assert schema.response_schema == json_schema

    def test_function_schema_response_schema_in_serialization(self):
        """response_schema is included in model_dump() output."""
        json_schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        schema = FunctionSchema(
            name="test",
            description="Test",
            http_methods=["GET"],
            parameters=[],
            response_schema=json_schema
        )
        data = schema.model_dump()
        assert "response_schema" in data
        assert data["response_schema"] == json_schema

    def test_function_schema_response_schema_none_in_serialization(self):
        """response_schema=None is serialized as null in model_dump()."""
        schema = FunctionSchema(
            name="test",
            description="Test",
            http_methods=["GET"],
            parameters=[]
        )
        data = schema.model_dump()
        assert "response_schema" in data
        assert data["response_schema"] is None

    def test_function_info_to_schema_includes_response_schema_with_test_output(self, sample_function):
        """to_schema() generates correct JSON Schema for TestOutput return type."""
        func_info = FunctionInfo(
            name="test_func",
            func=sample_function,
            description="Test function",
            params=[],
            return_type=TestOutput
        )
        schema = func_info.to_schema()

        assert schema.response_schema is not None
        assert isinstance(schema.response_schema, dict)
        assert "properties" in schema.response_schema
        props = schema.response_schema["properties"]
        assert "result" in props
        assert "success" in props
        assert "message" in props

    def test_function_info_to_schema_response_schema_none_when_no_return_type(self, sample_function):
        """to_schema() sets response_schema=None when return_type is None."""
        func_info = FunctionInfo(
            name="test_func",
            func=sample_function,
            description="Test function",
            params=[],
            return_type=None
        )
        schema = func_info.to_schema()
        assert schema.response_schema is None

    def test_function_info_to_schema_response_schema_with_custom_basemodel(self, sample_function):
        """to_schema() generates correct JSON Schema for a custom BaseModel return type."""
        class SearchResponse(BaseModel):
            users: List[str]
            total: int
            page: int = 1

        func_info = FunctionInfo(
            name="search_func",
            func=sample_function,
            description="Search function",
            params=[],
            return_type=SearchResponse
        )
        schema = func_info.to_schema()

        assert schema.response_schema is not None
        assert isinstance(schema.response_schema, dict)
        props = schema.response_schema["properties"]
        assert "users" in props
        assert "total" in props
        assert "page" in props

    def test_function_info_to_schema_response_schema_reflects_actual_type(self, sample_function):
        """response_schema matches the actual model_json_schema() of return_type."""
        func_info = FunctionInfo(
            name="test_func",
            func=sample_function,
            description="Test function",
            params=[],
            return_type=TestOutput
        )
        schema = func_info.to_schema()

        expected_schema = TestOutput.model_json_schema()
        assert schema.response_schema == expected_schema
