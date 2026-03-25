# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-03-25

### Added

- **Registry** — core decorator-based function registry (`@register_function()`) with
  automatic schema introspection from type hints and docstrings.
- **REST API** — FastAPI application factory (`Refract.api()`) exposing
  registered functions as GET/POST endpoints with automatic request/response
  validation via Pydantic.
- **CLI** — Click group factory (`Refract.cli()` / `Refract.run_cli`) that
  generates a command-line interface from the registry, including streaming
  support.
- **MCP integration** — FastAPI application factories (`Refract.mcp()` and
  `Refract.mcp_only()`) that expose registered functions as MCP tools, enabling
  AI-agent interoperability.
- **SSE streaming** — Server-Sent Events support for long-running functions,
  with helpers for both server-side emission and client-side consumption.
- **Web dashboard** — Built-in HTML dashboard (`/` and `/functions`) with a Lit-based
  web component (`<refract-element>`) for exploring and invoking registered
  functions directly from the browser.
- **JavaScript client** (`RefractClient`) — Vanilla JS HTTP client with schema
  loading, GET/POST dispatch, SSE streaming, and type coercion for `int`,
  `float`, `bool`, and complex JSON types.
- **Auto-discovery** — `discover` parameter on `Refract` to automatically
  import and register functions from specified Python modules.
- **Logging** — Structured logging configuration via `refract.log_config`.
- **`__all__`** export in `refract.py` to make the public API explicit.
