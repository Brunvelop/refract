"""FastAPI server with dynamic endpoints generated from a Refract registry."""
import logging
import os
from typing import Any, Callable, Dict, Type

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.routing import APIRouter
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, create_model

from refract.models import FunctionInfo
from refract.registry import Registry
from refract.sse import _create_stream_handler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API — instance-based (all entry points take a Registry instance)
# ---------------------------------------------------------------------------

def create_router(registry: Registry) -> APIRouter:
    """Create an ``APIRouter`` with only the dynamic endpoints from a Registry instance.

    This is the *router mode* — suitable for mounting on a user-supplied
    ``FastAPI`` app (``my_app.include_router(refract.router())``).

    Includes:
        - Dynamic function endpoints for all functions with ``"api"`` interface.
        - ``GET /functions/details`` — schema discovery for the frontend.
        - ``GET /health`` — basic health check.

    Excludes:
        - Static file mounts.
        - Root / functions HTML pages.

    Args:
        registry: A ``Registry`` instance whose registry will be used.

    Returns:
        An ``APIRouter`` ready to be included in any FastAPI application.
    """
    router = APIRouter()
    functions = registry.get_all_functions()
    _add_function_endpoints(router, functions, registry.get_stream_func)

    def _make_details_handler(registry_ref):
        async def list_functions_details() -> dict:
            schemas = registry_ref.get_all_schemas()
            return {"functions": {s.name: s for s in schemas}}
        return list_functions_details

    def _make_health_handler(registry_ref):
        async def health_check() -> dict:
            return {"status": "healthy", "functions": registry_ref.function_count()}
        return health_check

    router.add_api_route(
        "/functions/details",
        _make_details_handler(registry),
        methods=["GET"],
        operation_id="refract_list_functions_details",
        summary="List all registered function schemas",
    )
    router.add_api_route(
        "/health",
        _make_health_handler(registry),
        methods=["GET"],
        operation_id="refract_health_check",
        summary="Health check",
    )

    return router


def create_api_app(registry: Registry) -> FastAPI:
    """Create a complete ``FastAPI`` application for a ``Registry`` instance.

    Suitable for the *app mode*::

        app = Refract("my-project", discover=["my_project.core"])
        fastapi_app = app.api()  # Ready to serve

    Includes everything ``create_router`` produces, plus:
        - Standard HTML pages (root ``/``, ``/functions``).
        - Static file mounts (``/elements``).

    Args:
        registry: A ``Registry`` instance whose registry will be used.

    Returns:
        A configured ``FastAPI`` application.
    """
    try:
        from importlib.metadata import version as pkg_version
        _version = pkg_version("refract")
    except Exception:
        _version = "unknown"

    app = FastAPI(
        title=f"{registry.name} API",
        description=f"API for {registry.name}",
        version=_version,
    )

    # Reuse the router (dynamic endpoints + /functions/details + /health)
    router = create_router(registry)
    app.include_router(router)

    # App-mode exclusives: HTML pages + static files
    _register_html_pages(app)
    _register_static_files(app)

    return app


def create_handler(func_info: FunctionInfo, method: str):
    """Create endpoint handler for a registered function.

    Used by both ``api.py`` and ``mcp.py`` to create FastAPI handlers.

    Args:
        func_info: The function metadata from the registry.
        method: HTTP method string (``"GET"`` or ``"POST"``).

    Returns:
        Tuple of ``(handler_function, pydantic_model)``.
    """
    is_post = method.upper() == "POST"
    DynamicModel = _create_dynamic_model(func_info, for_post=is_post)

    if is_post:
        async def handler(request: DynamicModel):
            return _execute_function(func_info, request.model_dump(), method)
    else:
        async def handler(query_params: DynamicModel = Depends()):
            return _execute_function(func_info, query_params.model_dump(), method)

    return handler, DynamicModel


# ---------------------------------------------------------------------------
# Internal helpers — endpoint registration
# ---------------------------------------------------------------------------

def _add_function_endpoints(
    app_or_router,
    functions: list,
    stream_getter: Callable,
) -> None:
    """Register dynamic endpoints from a given list of FunctionInfo objects.

    This is the parameterised core — it does not touch any global registry.
    Both ``create_router`` and ``create_api_app`` delegate here.

    Args:
        app_or_router: A ``FastAPI`` app or ``APIRouter`` to add routes to.
        functions: List of ``FunctionInfo`` objects to register.
        stream_getter: Callable ``(name: str) -> Callable | None`` that returns
            the async generator for streaming functions.
    """
    api_functions = [f for f in functions if "api" in f.interfaces]

    for func_info in api_functions:
        if func_info.streaming:
            stream_func = stream_getter(func_info.name)
            if stream_func is None:
                logger.error(
                    f"Streaming function '{func_info.name}' has no stream_func registered"
                )
                continue
            DynamicModel = _create_dynamic_model(func_info, for_post=True)
            handler = _create_stream_handler(stream_func, DynamicModel)
            app_or_router.add_api_route(
                f"/{func_info.name}",
                handler,
                methods=["POST"],
                operation_id=f"{func_info.name}_stream",
                summary=f"[SSE Stream] {func_info.description}",
            )
        else:
            for method in func_info.http_methods:
                handler, _ = create_handler(func_info, method)
                response_model = func_info.return_type
                app_or_router.add_api_route(
                    f"/{func_info.name}",
                    handler,
                    methods=[method.upper()],
                    response_model=response_model,
                    operation_id=f"{func_info.name}_{method.lower()}",
                    summary=func_info.description,
                )

    logger.info(f"Registered {len(api_functions)} dynamic endpoints")


def _register_html_pages(app: FastAPI) -> None:
    """Register HTML page routes for the web UI (root and /functions).

    These are app-mode exclusives — ``create_router`` does not include them
    since they are not meaningful when the router is mounted on an existing app.

    Args:
        app: FastAPI application to register HTML routes on.
    """
    current_dir = os.path.dirname(__file__)
    views_dir = os.path.join(current_dir, "web", "views")

    @app.get("/")
    async def root():
        return FileResponse(os.path.join(views_dir, "functions.html"))

    @app.get("/functions")
    async def functions_ui():
        return FileResponse(os.path.join(views_dir, "functions.html"))


def _register_static_files(app: FastAPI) -> None:
    """Mount static files directories for web UI.

    Mounts ``refract/web/`` at ``/elements``, so JS files are served at:
        - ``/elements/client.js``
        - ``/elements/controller.js``
        - ``/elements/element.js``
        - ``/elements/generator.js``
    """
    current_dir = os.path.dirname(__file__)
    web_dir = os.path.join(current_dir, "web")

    if os.path.exists(web_dir):
        app.mount("/elements", StaticFiles(directory=web_dir), name="elements")


# ---------------------------------------------------------------------------
# Internal helpers — model generation
# ---------------------------------------------------------------------------

def _create_dynamic_model(func_info: FunctionInfo, for_post: bool = True) -> Type[BaseModel]:
    """Create a Pydantic model from function parameters.

    Args:
        func_info: Function metadata containing parameter definitions.
        for_post: If ``True``, creates an ``*Input`` model for POST body;
                  if ``False``, creates a ``*QueryParams`` model for GET query strings.

    Returns:
        A dynamically generated Pydantic model class.
    """
    fields = {}

    for param in func_info.params:
        if param.required:
            fields[param.name] = (param.type, Field(description=param.description))
        else:
            default = param.default if param.default is not None else None
            fields[param.name] = (param.type, Field(default=default, description=param.description))

    suffix = "Input" if for_post else "QueryParams"
    return create_model(f"{func_info.name.title()}{suffix}", **fields)


# ---------------------------------------------------------------------------
# Internal helpers — function execution
# ---------------------------------------------------------------------------

def _execute_function(
    func_info: FunctionInfo,
    request_params: Dict[str, Any],
    method: str,
) -> Dict[str, Any]:
    """Execute a registered function with parameters and handle errors.

    Args:
        func_info: Function metadata.
        request_params: Raw parameters from the request.
        method: HTTP method string (used for logging).

    Returns:
        Serialised response dict.

    Raises:
        HTTPException: 400 for parameter/type errors, 500 for runtime errors.
    """
    try:
        func_params = _extract_params(func_info, request_params)
        logger.debug(f"{method} {func_info.name}: params={func_params}")
        result = func_info.func(**func_params)
        return _format_response(result)
    except (ValueError, TypeError) as e:
        logger.warning(f"{method} {func_info.name} param error: {e}")
        raise HTTPException(status_code=400, detail=f"Parameter error: {e}")
    except Exception as e:
        logger.error(f"{method} {func_info.name} error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


def _extract_params(
    func_info: FunctionInfo,
    request_params: Dict[str, Any],
) -> Dict[str, Any]:
    """Extract known function parameters from raw request data.

    Ignores extra keys, fills in defaults (including ``None``) for missing
    optional params, and raises ``ValueError`` for missing required params.

    Args:
        func_info: Function metadata.
        request_params: Raw parameters dict from the HTTP request.

    Returns:
        Clean dict with only the params the function expects.

    Raises:
        ValueError: If a required parameter is absent from ``request_params``.
    """
    params = {}
    for param in func_info.params:
        if param.name in request_params:
            params[param.name] = request_params[param.name]
        elif param.required:
            raise ValueError(f"Missing required parameter: '{param.name}'")
        else:
            params[param.name] = param.default  # can be None, and that's fine
    return params


def _format_response(result: Any) -> Dict[str, Any]:
    """Format a function return value into an API response dict.

    - ``BaseModel`` → ``.model_dump()``
    - ``dict`` → returned as-is
    - anything else → raises ``TypeError`` (caught by ``_execute_function`` → HTTP 400)

    Args:
        result: The value returned by the registered function.

    Returns:
        A JSON-serialisable dict.

    Raises:
        TypeError: If the function returns a type other than ``BaseModel`` or ``dict``.
    """
    if isinstance(result, BaseModel):
        return result.model_dump()
    if isinstance(result, dict):
        return result
    raise TypeError(f"Function must return BaseModel or dict, got {type(result).__name__}")
