"""
Refract — facade class that wires the Registry with interface factories.

This module contains only the ``Refract`` class, which extends ``Registry``
with convenience methods that delegate to the interface adapters (API, CLI, MCP).

It is the **only module** that imports from all adapters. All other modules
depend only on ``Registry`` (the pure data layer), keeping the dependency
graph acyclic:

    refract.py → registry, api, cli, mcp
    api        → registry, models, sse
    cli        → registry, log_config
    mcp        → api, registry
    registry   → models
"""
from refract.registry import Registry
from refract.api import create_api_app, create_router
from refract.cli import create_cli
from refract.mcp import create_mcp_app


class Refract(Registry):
    """Registry + convenience interface factories.

    Extends :class:`~refract.registry.Registry` with ``api()``, ``cli()``,
    ``mcp()`` and ``router()`` factory methods, keeping the registry layer
    free of any adapter knowledge.

    Usage::

        app = Refract("my-project", discover=["my_project.core"])
        fastapi_app = app.api()   # REST API
        cli = app.cli()            # Click CLI
        mcp_app = app.mcp()        # MCP tools
    """

    def __init__(self, name: str, discover: list[str] | None = None) -> None:
        super().__init__(name, discover)
        self._cli_cached = None

    # ------------------------------------------------------------------
    # Interface factories
    # ------------------------------------------------------------------

    def api(self):
        """Create and return a complete FastAPI application for this instance.

        Returns:
            A configured ``FastAPI`` application.
        """
        return create_api_app(self)

    def router(self):
        """Create and return an ``APIRouter`` with only the dynamic endpoints.

        Returns:
            A ``fastapi.routing.APIRouter`` instance.
        """
        return create_router(self)

    def cli(self):
        """Create and return a Click group for this instance.

        Returns:
            A ``click.Group`` ready to serve as a CLI entry point.
        """
        return create_cli(self)

    def mcp(self):
        """Create and return a FastAPI application with API + MCP integration.

        Returns:
            A configured ``FastAPI`` application with MCP support.
        """
        return create_mcp_app(self)

    @property
    def run_cli(self):
        """Return the Click group for use as a ``pyproject.toml`` entry point.

        Enables zero-boilerplate entry points::

            # pyproject.toml
            [project.scripts]
            my-project = "my_project.app:app.run_cli"

        The result is cached so repeated property accesses return the same object.
        """
        if self._cli_cached is None:
            self._cli_cached = self.cli()
        return self._cli_cached
