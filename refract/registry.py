"""
Central registry for all functions exposed via interfaces (CLI, API, MCP).
Uses automatic parameter inference from function signatures and docstrings.

Example::

    from refract import register_function

    @register_function(http_methods=["GET", "POST"])
    def my_function(x: int, y: str = "default") -> MyResponse:
        '''Adds two numbers together.

        Args:
            x: First number
            y: Second number or string
        '''
        return MyResponse(result=x + y)

    # Entry point
    from refract import Refract
    app = Refract("my-project", discover=["my_project.core"])
"""
from typing import Any, Callable, get_origin, get_args, Union, Literal
import ast
import importlib
import importlib.util
import inspect
import logging
import pkgutil
from docstring_parser import parse

from pydantic import BaseModel
from refract.models import (
    FunctionInfo, ParamSchema, FunctionSchema,
    HttpMethod, Interface, DEFAULT_HTTP_METHODS, DEFAULT_INTERFACES
)

logger = logging.getLogger(__name__)


# --- PRIVATE STATE ---

# Buffer for pending registrations (used by Refract._drain_pending())
_pending_registrations: list[FunctionInfo] = []
_pending_stream_funcs: dict[str, Callable] = {}


class RegistryError(Exception):
    """Custom exception for registry-related errors."""
    pass


# --- PUBLIC API ---

def register_function(
    http_methods: list[HttpMethod] | None = None,
    interfaces: list[Interface] | None = None,
    streaming: bool = False,
    stream_func: Callable | None = None
) -> Callable[[Callable], Callable]:
    """Decorator to expose a function via CLI, API, and/or MCP.

    Args:
        http_methods: HTTP methods to expose (default: GET, POST).
        interfaces: Interfaces to expose on (default: api, cli, mcp).
        streaming: Whether this function supports SSE streaming.
        stream_func: Async generator function for streaming. Required if streaming=True.
    """
    def decorator(func: Callable) -> Callable:
        try:
            # Validation: streaming=True requires stream_func
            if streaming and stream_func is None:
                raise RegistryError(
                    f"Function '{func.__name__}': streaming=True requires stream_func"
                )

            info = _generate_function_info(func, http_methods, interfaces)
            info.streaming = streaming

            # Check for duplicates against pending buffer only
            if any(f.name == info.name for f in _pending_registrations):
                raise RegistryError(f"Function '{info.name}' is already registered")

            _pending_registrations.append(info)

            # Store stream_func in pending buffer
            if stream_func is not None:
                _pending_stream_funcs[info.name] = stream_func

            logger.debug(f"Registered '{info.name}' with methods {info.http_methods}, streaming={streaming}")
        except Exception as e:
            raise RegistryError(f"Failed to register function '{func.__name__}': {e}") from e
        return func
    return decorator


def _clear_pending() -> None:
    """Clear pending buffers. Used for testing."""
    _pending_registrations.clear()
    _pending_stream_funcs.clear()


# --- PRIVATE IMPLEMENTATION ---

def _generate_function_info(
    func: Callable,
    http_methods: list[HttpMethod] | None = None,
    interfaces: list[Interface] | None = None
) -> FunctionInfo:
    """Generate FunctionInfo from function signature and docstring."""
    http_methods = http_methods or list(DEFAULT_HTTP_METHODS)
    interfaces = interfaces or list(DEFAULT_INTERFACES)

    # Validate HTTP methods
    valid_methods = {"GET", "POST", "PUT", "DELETE", "PATCH"}
    if not all(m.upper() in valid_methods for m in http_methods):
        raise ValueError(f"Invalid HTTP methods. Must be one of: {valid_methods}")

    # Validate return type
    sig = inspect.signature(func)
    return_annotation = sig.return_annotation

    if return_annotation == inspect.Parameter.empty:
        raise RegistryError(f"Function '{func.__name__}' must have a return type annotation of BaseModel")

    # Resolve Optional/Union to inner type
    return_type = return_annotation
    if get_origin(return_annotation) is Union:
        non_none = [a for a in get_args(return_annotation) if a is not type(None)]
        if non_none:
            return_type = non_none[0]

    if not (isinstance(return_type, type) and issubclass(return_type, BaseModel)):
        raise RegistryError(f"Function '{func.__name__}' must return BaseModel, got {return_type}")

    # Parse docstring for parameter descriptions
    doc = parse(inspect.getdoc(func) or "")
    param_docs = {p.arg_name: p.description for p in doc.params}

    # Extract parameters
    params = []
    for name, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        params.append(_extract_param_info(param, name, param_docs))

    return FunctionInfo(
        name=func.__name__,
        func=func,
        description=doc.short_description or f"Execute {func.__name__}",
        params=params,
        http_methods=http_methods,
        interfaces=interfaces,
        return_type=return_type
    )


def _extract_param_info(param: inspect.Parameter, name: str, param_docs: dict[str, str]) -> ParamSchema:
    """Extract ParamSchema from inspect.Parameter."""
    param_type = param.annotation if param.annotation != inspect.Parameter.empty else Any
    choices = list(get_args(param_type)) if get_origin(param_type) is Literal else None

    return ParamSchema(
        name=name,
        type=param_type,
        default=param.default if param.default != inspect.Parameter.empty else None,
        required=param.default == inspect.Parameter.empty,
        description=param_docs.get(name, f"Parameter {name}"),
        choices=choices
    )


def _get_module_file_path(module_name: str) -> str | None:
    """Return file path for a module, or None if not found."""
    try:
        spec = importlib.util.find_spec(module_name)
        return spec.origin if spec else None
    except Exception:
        return None


def _has_register_decorator(module_path: str | None) -> bool:
    """Check if module contains @register_function decorator using AST."""
    if not module_path:
        return False
    try:
        with open(module_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=module_path)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if isinstance(dec, ast.Name) and dec.id == 'register_function':
                    return True
                if isinstance(dec, ast.Call):
                    func = dec.func
                    if isinstance(func, ast.Name) and func.id == 'register_function':
                        return True
                    if isinstance(func, ast.Attribute) and func.attr == 'register_function':
                        return True
                if isinstance(dec, ast.Attribute) and dec.attr == 'register_function':
                    return True
        return False
    except Exception:
        return False


# --- REFRACT CLASS ---

class Refract:
    """Instance-based registry that owns its own set of registered functions.

    Allows multiple isolated registries in the same process, enabling
    multi-project setups and clean test isolation.

    Usage::

        app = Refract("my-project", discover=["my_project.core"])
        # @register_function-decorated functions in my_project.core are now
        # associated with this instance's registry.

    The ``discover`` flow uses the same buffer pattern as Celery:
    - ``@register_function()`` decorators fire when modules are imported,
      writing to the global ``_pending_registrations`` buffer.
    - ``Refract.__init__`` always calls ``_drain_pending()`` at the end,
      which collects everything in the buffer into this instance and clears it.

    This means ``Refract()`` without ``discover`` will also drain any pending
    registrations that were decorated before instantiation.
    """

    def __init__(self, name: str, discover: list[str] | None = None) -> None:
        """Initialise a Refract registry instance.

        Args:
            name: Human-readable name for this instance (e.g. ``"my-project"``).
            discover: List of package paths to scan for ``@register_function``
                decorators (e.g. ``["my_project.core"]``). When provided,
                ``_discover()`` is called immediately during ``__init__``.
        """
        self.name = name
        self._registry: list[FunctionInfo] = []
        self._stream_registry: dict[str, Callable] = {}
        self._custom_commands: list[tuple[str, Callable, dict]] = []

        if discover:
            self._discover(discover)

        self._drain_pending()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _drain_pending(self) -> None:
        """Drain the global pending buffer into this instance's registry."""
        self._registry.extend(_pending_registrations)
        self._stream_registry.update(_pending_stream_funcs)
        _pending_registrations.clear()
        _pending_stream_funcs.clear()

    def _discover(self, packages: list[str], strict: bool = False) -> None:
        """Import modules in *packages* and collect pending registrations.

        For each package path in *packages*:
        1. Walk all sub-modules using ``pkgutil.walk_packages``.
        2. Skip modules that don't contain ``@register_function`` (AST scan).
        3. Import each qualifying module — this fires the decorators, which
           write to the global ``_pending_registrations`` buffer.

        Note: draining the buffer is handled by ``_drain_pending()``, which
        ``__init__`` always calls after ``_discover``.

        Args:
            packages: List of dotted package names to scan.
            strict: If ``True``, raise ``RegistryError`` on the first
                import failure instead of logging and continuing.
        """
        failed: list[tuple[str, str]] = []

        for package_path in packages:
            try:
                pkg = importlib.import_module(package_path)
            except ImportError as e:
                raise RegistryError(
                    f"[Refract:{self.name}] Failed to import package '{package_path}': {e}"
                ) from e

            pkg_file = getattr(pkg, "__path__", None)
            if pkg_file is None:
                logger.warning(
                    f"[Refract:{self.name}] '{package_path}' has no __path__; skipping."
                )
                continue

            modules = sorted(
                pkgutil.walk_packages(pkg_file, pkg.__name__ + "."),
                key=lambda x: x[1],
            )

            logger.info(f"[refract:{self.name}] Scanning {package_path}...")

            for _, module_name, is_pkg in modules:
                if is_pkg:
                    continue
                module_path_str = _get_module_file_path(module_name)
                if not _has_register_decorator(module_path_str):
                    logger.debug(f"[refract:{self.name}]   ℹ️  {module_name} — no @register_function found")
                    continue
                before = len(_pending_registrations)
                try:
                    importlib.import_module(module_name)
                    n_funcs = len(_pending_registrations) - before
                    logger.info(f"[refract:{self.name}]   ✅ {module_name} — {n_funcs} function{'s' if n_funcs != 1 else ''}")
                except Exception as e:
                    failed.append((module_name, str(e)))
                    logger.warning(
                        f"[refract:{self.name}]   ⚠️  {module_name} — skipped ({type(e).__name__}: {e})"
                    )

        total_funcs = len(self._registry) + len(_pending_registrations)
        logger.info(
            f"[refract:{self.name}] Total: {total_funcs} function{'s' if total_funcs != 1 else ''} registered"
            + (f", {len(failed)} module{'s' if len(failed) != 1 else ''} skipped" if failed else "")
        )

        if failed and strict:
            raise RegistryError(
                f"[Refract:{self.name}] Failed to load modules in strict mode: "
                f"{[m[0] for m in failed]}"
            )

    # ------------------------------------------------------------------
    # Instance-level query API
    # ------------------------------------------------------------------

    def get_all_functions(self) -> list[FunctionInfo]:
        """Return all functions registered in this instance."""
        return list(self._registry)

    def get_functions_for_interface(self, interface: Interface) -> list[FunctionInfo]:
        """Filter functions by interface.

        Args:
            interface: One of ``"api"``, ``"cli"``, or ``"mcp"``.
        """
        return [f for f in self._registry if interface in f.interfaces]

    def get_all_schemas(self) -> list[FunctionSchema]:
        """Return serialisable schemas for all functions in this instance."""
        return [info.to_schema() for info in self._registry]

    def get_function_by_name(self, name: str) -> FunctionInfo | None:
        """Look up a function by name.

        Args:
            name: Exact function name.
        """
        return next((f for f in self._registry if f.name == name), None)

    def get_stream_func(self, name: str) -> Callable | None:
        """Return the streaming callable for a registered function.

        Args:
            name: Function name.
        """
        return self._stream_registry.get(name)

    def function_count(self) -> int:
        """Return the number of functions registered in this instance."""
        return len(self._registry)

    def clear(self) -> None:
        """Remove all functions from this instance (does not touch the pending buffer)."""
        self._registry.clear()
        self._stream_registry.clear()

    # ------------------------------------------------------------------
    # Interface factories
    # ------------------------------------------------------------------

    def api(self):
        """Create and return a complete FastAPI application for this instance.

        Returns:
            A configured ``FastAPI`` application.
        """
        from refract.api import create_api_app_for_refract
        return create_api_app_for_refract(self)

    def router(self):
        """Create and return an ``APIRouter`` with only the dynamic endpoints.

        Returns:
            A ``fastapi.routing.APIRouter`` instance.
        """
        from refract.api import create_router_for_refract
        return create_router_for_refract(self)

    def cli(self):
        """Create and return a Click group for this instance.

        Returns:
            A ``click.Group`` ready to serve as a CLI entry point.
        """
        from refract.cli import create_cli_for_refract
        return create_cli_for_refract(self)

    def command(self, name: str | None = None, **kwargs):
        """Decorator to register a custom CLI command on this instance.

        Args:
            name: Optional command name override.
            **kwargs: Additional keyword arguments forwarded to ``click.Group.command()``.
        """
        def decorator(func: Callable) -> Callable:
            cmd_name = name if name is not None else func.__name__.replace('_', '-')
            self._custom_commands.append((cmd_name, func, kwargs))
            return func
        return decorator

    @property
    def run_cli(self):
        """Return the Click group for use as a ``pyproject.toml`` entry point.

        Enables zero-boilerplate entry points::

            # pyproject.toml
            [project.scripts]
            my-project = "my_project.app:app.run_cli"

        The result is cached so repeated property accesses return the same object.
        """
        if not hasattr(self, '_cli_cached'):
            self._cli_cached = self.cli()
        return self._cli_cached

    def mcp(self):
        """Create and return a FastAPI application with API + MCP integration.

        Returns:
            A configured ``FastAPI`` application with MCP support.
        """
        from refract.mcp import create_mcp_app_for_refract
        return create_mcp_app_for_refract(self)

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"Refract(name={self.name!r}, functions={self.function_count()})"
