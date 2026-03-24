"""
Refract — Refract a Python function into multiple interfaces.

Define a Python function with type hints and a docstring, and automatically get:
- REST API (FastAPI)
- CLI (Click)
- MCP tools (for agents/LLMs)
- Web UI auto-generated (Web Components)
- Shared back↔front schema

Usage::

    from pydantic import BaseModel
    from refract import Refract, register_function

    class Sum(BaseModel):
        result: int

    @register_function()
    def add(a: int, b: int) -> Sum:
        \"\"\"Add two numbers.
        Args:
            a: First number
            b: Second number
        \"\"\"
        return Sum(result=a + b)

    app = Refract("my-project", discover=["my_project.core"])
    fastapi_app = app.api()   # REST API
    cli = app.cli()            # Click CLI
    mcp_app = app.mcp()        # MCP tools
"""

__version__ = "0.1.0"

__all__ = [
    # Core framework class
    "Refract",
    # Decorator
    "register_function",
    # Models
    "ParamSchema",
    "FunctionInfo",
    "FunctionSchema",
]

from refract.models import ParamSchema, FunctionInfo, FunctionSchema
from refract.registry import Refract, register_function
