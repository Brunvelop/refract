"""
Shared Pydantic models for core functions and all interfaces (CLI, API, MCP).
These models define the input/output contracts for functions registered in the registry.
"""

__all__ = ["ParamSchema", "FunctionInfo", "FunctionSchema", "HttpMethod", "Interface", "DEFAULT_HTTP_METHODS", "DEFAULT_INTERFACES"]

from pydantic import BaseModel, Field, ConfigDict, field_serializer
from typing import Any, Callable, Literal, Union, get_origin, get_args


# --- Type Definitions & Constants ---

HttpMethod = Literal["GET", "POST", "PUT", "DELETE", "PATCH"]
Interface = Literal["api", "cli", "mcp"]
DEFAULT_HTTP_METHODS: list[HttpMethod] = ["GET", "POST"]
DEFAULT_INTERFACES: list[Interface] = ["api", "cli", "mcp"]


# --- Unified Parameter Model ---

class ParamSchema(BaseModel):
    """
    Unified parameter model for runtime and serialization.
    
    Stores Python types at runtime (for create_model, Click mapping, etc.)
    and automatically serializes to strings for JSON/OpenAPI.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    name: str = Field(description="Parameter name")
    type: Any = Field(description="Parameter type (Python type at runtime, string when serialized)")
    default: Any | None = Field(default=None, description="Default value")
    required: bool = Field(description="Whether the parameter is required")
    description: str = Field(description="Parameter description")
    choices: list[Any] | None = Field(default=None, description="Available choices for Literal types")

    @field_serializer('type')
    def serialize_type_field(self, v: Any) -> str:
        """Serialize Python type to string for JSON/OpenAPI."""
        return self._serialize_type(v)

    @property
    def type_str(self) -> str:
        """Get type as string (for display purposes)."""
        return self._serialize_type(self.type)

    def to_schema(self) -> "ParamSchema":
        """Returns self (for backwards compatibility with ExplicitParam API)."""
        return self

    def _serialize_type(self, t: Any) -> str:
        """Serializes Python type to string, including generics.
        
        Supports:
        - Basic types: int, str, float, bool, list, dict, tuple
        - Generic types: list[str], dict[str, int], tuple[int, str]
        - Optional: str | None -> "str?"
        - Union: str | int -> "str | int"
        - Literal: Literal["a", "b"] -> "Literal['a', 'b']"
        - Nested types: list[dict[str, int]] -> "list[dict[str, int]]"
        """
        # Generic types (list[str], dict[str, int], str | None, etc.)
        origin = get_origin(t)
        if origin is not None:
            args = get_args(t)
            
            # Optional[X] is Union[X, None] - detect and convert to "X?"
            if origin is Union:
                non_none_args = [a for a in args if a is not type(None)]
                # If it's Optional (Union with a single type + None)
                if len(non_none_args) == 1 and type(None) in args:
                    return f"{self._serialize_type(non_none_args[0])}?"
                # Normal Union: "str | int"
                return " | ".join(self._serialize_type(a) for a in args)
            
            # Literal['a', 'b'] -> "Literal['a', 'b']"
            if origin is Literal:
                args_str = ", ".join(repr(a) for a in args)
                return f"Literal[{args_str}]"
            
            # list[X], dict[K, V], tuple[X, Y], etc.
            origin_name = getattr(origin, '__name__', str(origin)).lower()
            if args:
                args_str = ", ".join(self._serialize_type(a) for a in args)
                return f"{origin_name}[{args_str}]"
            return origin_name
            
        # If it has __name__ (classes, native types)
        if hasattr(t, '__name__'):
            return t.__name__
            
        # Fallback to string representation
        return str(t)


class FunctionSchema(BaseModel):
    """Serializable schema for a function (API contract)."""
    name: str = Field(description="Function name")
    description: str = Field(description="Function description")
    http_methods: list[HttpMethod] = Field(description="Supported HTTP methods")
    interfaces: list[Interface] = Field(default_factory=lambda: list(DEFAULT_INTERFACES), description="Interfaces where this function is exposed")
    parameters: list[ParamSchema] = Field(description="Function parameters")
    streaming: bool = Field(default=False, description="Whether this function supports SSE streaming")
    response_schema: dict | None = Field(default=None, description="JSON Schema of the response model")


# --- Runtime Models (Internal Registry) ---

class FunctionInfo(BaseModel):
    """Function information for the registry with explicit parameters."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    name: str
    func: Callable
    description: str
    params: list[ParamSchema] = Field(default_factory=list, description="Parameter definitions")
    http_methods: list[HttpMethod] = Field(default_factory=lambda: list(DEFAULT_HTTP_METHODS))
    interfaces: list[Interface] = Field(default_factory=lambda: list(DEFAULT_INTERFACES), description="Interfaces where this function is exposed")
    # Return type annotation (BaseModel subclass). Useful for typing the response_model in FastAPI.
    return_type: type[BaseModel] | None = Field(default=None, description="Declared return type annotation")
    streaming: bool = Field(default=False, description="Whether this function supports SSE streaming")

    def to_schema(self) -> FunctionSchema:
        """Converts to serializable schema."""
        return FunctionSchema(
            name=self.name,
            description=self.description,
            http_methods=self.http_methods,
            interfaces=self.interfaces,
            parameters=self.params,  # ParamSchema serializes automatically
            streaming=self.streaming,
            response_schema=self.return_type.model_json_schema() if self.return_type else None
        )

