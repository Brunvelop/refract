"""
CLI interface using Click with dynamic commands from a Refract instance.

This module provides a command-line interface for the Refract framework,
automatically generating CLI commands from functions registered in a
``Refract`` instance. All entry points take a ``Refract`` instance — there
is no global state or auto-initialization.

Usage::

    from refract import Refract

    app = Refract("my-project", discover=["my_project.core"])

    # Entry point for pyproject.toml
    # [project.scripts]
    # my-project = "my_project.app:app.run_cli"
"""
import click
import uvicorn
from typing import Dict, Any, Callable, Optional

from refract.api import create_api_app
from refract.log_config import configure_cli_logging
from refract.mcp import create_mcp_app, create_mcp_only_app
from refract.registry import Registry


# ============================================================================
# CONFIGURATION
# ============================================================================

# Type mapping for Click options - maps Python types to Click parameter types
TYPE_MAP: Dict[type, Any] = {
    int: click.INT,
    float: click.FLOAT,
    bool: click.BOOL,
    str: click.STRING,
}


# ============================================================================
# REFRACT INSTANCE API
# ============================================================================

def create_cli(registry: Registry) -> click.Group:
    """Create a complete Click group driven by a ``Registry`` instance.

    All commands are bound to the instance registry.  There is no global
    ``app`` object or auto-initialization side effect.

    Includes:
        - ``list``      — lists functions in this instance's registry.
        - ``serve-api`` — starts FastAPI server via ``create_api_app(registry)``.
        - ``serve-mcp`` — starts API+MCP server via ``create_mcp_app(registry)``.
        - ``serve``     — alias for ``serve-mcp`` (recommended default).
        - Dynamic function commands for all ``"cli"``-interface functions.
        - Custom commands registered via ``@registry.command()``.

    Args:
        registry: A ``Registry`` instance whose registry and custom commands
            are used to build the Click group.

    Returns:
        A ``click.Group`` ready to serve as a CLI entry point.
    """
    @click.group(help=f"{registry.name} CLI")
    @click.option('--verbose', '-v', is_flag=True, help='Enable verbose output (DEBUG level)')
    @click.pass_context
    def cli_group(ctx, verbose):
        configure_cli_logging(verbose=verbose)
        ctx.ensure_object(dict)
        ctx.obj['verbose'] = verbose

    @cli_group.command("list")
    def list_cmd():
        """List all available functions in the registry."""
        click.echo("Available functions:")
        for func_info in registry.get_all_functions():
            click.echo(f"  {func_info.name}: {func_info.description}")
            schema = func_info.to_schema()
            params = schema.parameters
            if params:
                click.echo(f"    Parameters:")
                for param in params:
                    param_str = f"{param.name} ({param.type_str})"
                    if not param.required:
                        param_str += f" = {param.default}"
                    else:
                        param_str += " (required)"
                    if param.description != f"Parameter {param.name}":
                        param_str += f" - {param.description}"
                    click.echo(f"      {param_str}")

    @cli_group.command("serve-api")
    @click.option("--host", default="127.0.0.1", help="Host to bind to")
    @click.option("--port", default=8000, type=int, help="Port to bind to")
    def serve_api_cmd(host: str, port: int):
        """Start the API server (REST endpoints only)."""
        click.echo(f"Starting {registry.name} API server on {host}:{port}")
        api_app = create_api_app(registry)
        uvicorn.run(api_app, host=host, port=port)

    @cli_group.command("serve-mcp")
    @click.option("--host", default="127.0.0.1", help="Host to bind to")
    @click.option("--port", default=8001, type=int, help="Port to bind to")
    def serve_mcp_cmd(host: str, port: int):
        """Start MCP-only server (no REST API endpoints)."""
        click.echo(f"Starting {registry.name} MCP-only server on {host}:{port}")
        mcp_only_app = create_mcp_only_app(registry)
        uvicorn.run(mcp_only_app, host=host, port=port)

    @cli_group.command("serve")
    @click.option("--host", default="0.0.0.0", help="Host to bind to")
    @click.option("--port", default=8000, type=int, help="Port to bind to")
    def serve_cmd(host: str, port: int):
        """Start the unified server with both API and MCP (recommended)."""
        click.echo(f"Starting {registry.name} unified server (API + MCP) on {host}:{port}")
        unified_app = create_mcp_app(registry)
        uvicorn.run(unified_app, host=host, port=port)

    # Register dynamic function commands from the instance registry
    _register_commands(cli_group, registry)

    # Register custom commands added via @registry.command()
    for cmd_name, cmd_func, cmd_kwargs in registry._custom_commands:
        cli_group.command(name=cmd_name, **cmd_kwargs)(cmd_func)

    return cli_group


def _register_commands(cli_group: click.Group, registry: Registry) -> None:
    """Register dynamic CLI commands from a Registry instance.

    Only functions that include ``"cli"`` in their ``interfaces`` list are
    added as commands.

    Args:
        cli_group: The Click group to add commands to.
        registry: Registry instance whose ``"cli"``-interface functions are used.
    """
    cli_functions = registry.get_functions_for_interface("cli")
    for func_info in cli_functions:
        command_func = _create_handler(func_info.name, func_info)
        command_func = _add_command_options(command_func, func_info.params)
        cli_group.command(name=func_info.name, help=func_info.description)(command_func)


# ============================================================================
# PRIVATE HELPERS - COMMAND GENERATION
# ============================================================================

def _get_click_type(param_type: type, choices: Optional[list] = None) -> Any:
    """Get appropriate Click type for parameter.

    Maps Python types to Click parameter types with support for choices.

    Args:
        param_type: Python type annotation from function signature
        choices: Optional list of valid choices (from Literal types)

    Returns:
        Click type object suitable for option/argument definition
    """
    if choices:
        return click.Choice(choices)
    return TYPE_MAP.get(param_type, click.STRING)


def _add_command_options(command_func: Callable, params: list) -> Callable:
    """Add Click options to command function from parameter definitions.

    Iterates through function parameters and adds corresponding Click options
    in reverse order (Click requirement for proper option handling).

    Args:
        command_func: Function to decorate with Click options
        params: List of ParamSchema objects from function registry

    Returns:
        Decorated function with Click options attached
    """
    for param in reversed(params):
        click_type = _get_click_type(param.type, param.choices)
        option_name = f"--{param.name.replace('_', '-')}"

        option_kwargs = {
            "type": click_type,
            "required": param.required,
            "help": param.description,
        }

        if not param.required:
            option_kwargs["default"] = param.default

        command_func = click.option(option_name, **option_kwargs)(command_func)

    return command_func


def _prepare_function_params(func_info, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare function parameters from CLI arguments.

    Filters and processes CLI arguments to match function signature,
    handling defaults and required parameters appropriately.

    Args:
        func_info: FunctionInfo object with parameter metadata
        kwargs: Dictionary of arguments from Click command

    Returns:
        Dictionary of parameters ready for function execution
    """
    func_params = {}
    for param in func_info.params:
        if param.name in kwargs and kwargs[param.name] is not None:
            func_params[param.name] = kwargs[param.name]
        elif not param.required and param.default is not None:
            func_params[param.name] = param.default
        elif param.required:
            func_params[param.name] = kwargs.get(param.name)
    return func_params


def _create_handler(func_name: str, func_info) -> Callable:
    """Create a command handler for a specific function.

    Generates a Click-compatible command function that executes a registered
    function with proper parameter handling and error management.

    Args:
        func_name: Name of the function (for logging/errors)
        func_info: FunctionInfo object with function and metadata

    Returns:
        Command function ready to be registered with Click
    """
    def command_func(**kwargs):
        """Execute the registered function with provided arguments."""
        try:
            func_params = _prepare_function_params(func_info, kwargs)
            result = func_info.func(**func_params)
            click.echo(result)
        except Exception as e:
            click.echo(f"Error executing {func_name}: {str(e)}", err=True)
            raise click.Abort()

    command_func.__name__ = f"{func_name}_command"
    command_func.__doc__ = func_info.description

    return command_func
