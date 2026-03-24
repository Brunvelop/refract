"""
MCP (Model Context Protocol) integration using fastapi_mcp.

This module provides integration between the Refract API and the Model Context
Protocol, allowing API endpoints to be exposed as MCP tools for use with AI
assistants and other MCP-compatible clients.

All entry points are instance-based — there is no global ``create_mcp_app()``
or global registry access.

Usage::

    from refract import Refract

    app = Refract("my-project", discover=["my_project.core"])
    mcp_app = app.mcp()       # FastAPI app with full API + MCP support
    mcp_only = app.mcp_only() # FastAPI app with MCP endpoints only
"""
__all__ = ["create_mcp_app", "create_mcp_only_app"]

import logging
from fastapi import FastAPI
from fastapi_mcp import FastApiMCP

from refract.api import create_api_app, create_handler
from refract.registry import Registry

logger = logging.getLogger(__name__)


# ============================================================================
# REFRACT INSTANCE API
# ============================================================================

def _register_mcp_endpoints(app: FastAPI, registry: Registry) -> None:
    """Register MCP endpoints from a Registry instance.

    Only functions that include ``"mcp"`` in their ``interfaces`` list are
    exposed as MCP tool endpoints (tagged ``"mcp-tools"``).

    Args:
        app: FastAPI application to register endpoints on.
        registry: A ``Registry`` instance whose ``"mcp"``-interface functions
            are exposed as MCP tool endpoints.
    """
    mcp_functions = registry.get_functions_for_interface("mcp")

    for func_info in mcp_functions:
        for method in func_info.http_methods:
            handler, input_model = create_handler(func_info, method)
            response_model = func_info.return_type

            app.add_api_route(
                f"/{func_info.name}",
                handler,
                methods=[method.upper()],
                response_model=response_model,
                operation_id=f"mcp_{func_info.name}_{method.lower()}",
                summary=func_info.description,
                tags=["mcp-tools"],
            )

    logger.info(f"[Refract:{registry.name}] Registered {len(mcp_functions)} MCP endpoints")


def create_mcp_only_app(registry: Registry) -> FastAPI:
    """Create a minimal FastAPI application exposing only MCP endpoints.

    Unlike ``create_mcp_app``, this function does **not** build on top of the
    full REST API application.  It creates a bare ``FastAPI`` instance and
    registers only the functions whose ``interfaces`` list includes ``"mcp"``.

    Steps:
        1. Create a fresh ``FastAPI`` app (no ``create_api_app``).
        2. Register a minimal ``/health`` endpoint.
        3. Register only the MCP-interface endpoints (tagged ``"mcp-tools"``).
        4. Initialise and mount the ``FastApiMCP`` server.

    No HTML pages, static files, or general REST endpoints are included.
    Suitable for deployments where the MCP surface should be isolated from
    the REST API (e.g. a dedicated MCP sidecar).

    Args:
        registry: A ``Registry`` instance whose ``"mcp"``-interface functions
            are exposed as MCP tool endpoints.

    Returns:
        A configured ``FastAPI`` application with MCP-only support.

    Raises:
        RuntimeError: If MCP server initialisation fails.
    """
    try:
        # Step 1: Create a bare FastAPI app (no full API layer)
        app = FastAPI(
            title=f"{registry.name} MCP Server",
            description=f"MCP-only server for {registry.name}",
        )

        # Step 2: Minimal /health endpoint (useful for container health checks)
        @app.get("/health", tags=["health"])
        async def health_check() -> dict:
            return {"status": "healthy", "server": registry.name, "mode": "mcp-only"}

        # Step 3: Register only MCP-interface endpoints
        _register_mcp_endpoints(app, registry)

        # Step 4: Initialise MCP server — include only mcp-tools tagged endpoints
        mcp = FastApiMCP(
            app,
            name=f"{registry.name} MCP Server",
            description=f"MCP server for {registry.name}",
            include_tags=["mcp-tools"],
        )

        # Step 5: Mount MCP server with Streamable HTTP transport
        mcp.mount_http()

        logger.info(f"[Refract:{registry.name}] Successfully created MCP-only app")
        return app

    except Exception as e:
        logger.error(f"[Refract:{registry.name}] Failed to create MCP-only app: {str(e)}")
        raise RuntimeError(f"MCP server initialization failed: {str(e)}") from e


def create_mcp_app(registry: Registry) -> FastAPI:
    """Create a FastAPI application with API + MCP integration for a Registry instance.

    Steps:
        1. Build the base FastAPI app via ``create_api_app``.
        2. Update app metadata to reflect MCP integration.
        3. Register MCP-specific endpoints from the instance registry.
        4. Initialise and mount the FastApiMCP server.

    Args:
        registry: A ``Registry`` instance whose registry drives both the API
            and the MCP tool endpoints.

    Returns:
        A configured ``FastAPI`` application with MCP support.

    Raises:
        RuntimeError: If MCP server initialisation fails.
    """
    try:
        # Step 1: Create base API application from the instance registry
        app = create_api_app(registry)

        # Step 2: Update app metadata to reflect MCP integration
        app.title = f"{registry.name} API + MCP Server"
        app.description = f"API and MCP server for {registry.name}"

        # Step 3: Register MCP-specific endpoints (only functions with "mcp" interface)
        _register_mcp_endpoints(app, registry)

        # Step 4: Initialise MCP server — include only mcp-tools tagged endpoints
        mcp = FastApiMCP(
            app,
            name=f"{registry.name} MCP Server",
            description=f"MCP server for {registry.name} functions and API endpoints",
            include_tags=["mcp-tools"],
        )

        # Step 5: Mount MCP server with Streamable HTTP transport (modern)
        mcp.mount_http()

        logger.info(f"[Refract:{registry.name}] Successfully created MCP app with API integration")
        return app

    except Exception as e:
        logger.error(f"[Refract:{registry.name}] Failed to create MCP app: {str(e)}")
        raise RuntimeError(f"MCP server initialization failed: {str(e)}") from e
