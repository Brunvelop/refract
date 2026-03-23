"""
Refract — Refract a Python function into multiple interfaces.

Define a Python function with type hints and a docstring, and automatically get:
- REST API (FastAPI)
- CLI (Click)
- MCP tools (for agents/LLMs)
- Web UI auto-generated (Web Components)
- Shared back↔front schema

Usage::

    from refract import Refract, register_function, GenericOutput

    @register_function()
    def add(a: int, b: int) -> GenericOutput:
        \"\"\"Add two numbers.
        Args:
            a: First number
            b: Second number
        \"\"\"
        return GenericOutput(result=a + b)

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
    "GenericOutput",
    "ParamSchema",
    "FunctionInfo",
    "FunctionSchema",
]

# Imports will be available once Commit 2 adds models.py and registry.py
from refract.models import GenericOutput, ParamSchema, FunctionInfo, FunctionSchema
from refract.registry import Refract, register_function
