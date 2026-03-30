# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`RefractClient.execute(funcName, params)`** — Static helper to execute a registered function
  without any DOM dependency (absorbs logic previously in `AutoFunctionController.executeFunction()`).
- **`RefractClient.validate(params, funcInfo)`** — Pure utility for validating parameters against
  the function schema (absorbs logic previously in the controller).

### Changed

- **`AutoFunctionElement` is now self-contained** — Extends `LitElement` directly and uses
  `RefractClient` via composition instead of inheriting from `AutoFunctionController`.
  The public API (`func-name` attribute, interactive card) remains unchanged.
- **Dashboard** — `dashboard.html` now creates `<auto-function-element func-name="...">` elements
  directly instead of relying on `AutoElementGenerator`.

### Removed

- **`AutoFunctionController`** (`controller.js`) — The Lit controller base class has been removed.
  `AutoFunctionElement` is now self-contained and no longer requires this intermediate layer.
- **`AutoElementGenerator`** (`generator.js`) — The zero-config element generator has been removed.
  Use `<auto-function-element func-name="...">` directly instead of auto-generated per-function tags.

## [1.1.0] - 2026-03-28

### Added

- **`Registry.current()` / `Refract.current()`** — Flask `current_app` pattern.
  Returns the most recently created instance; raises `RuntimeError` if none exists.
  Useful in business-logic modules that must not import the app module directly.
- **Custom views and static dirs** — `Registry` / `Refract` now accept `views`
  (URL path → HTML file mapping) and `static_dirs` (list of `(mount_path, dir)`
  tuples). When `views` is provided it replaces the default dashboard routes;
  `static_dirs` mounts additional static directories alongside the SDK.
  The `/refract/` namespace is reserved for SDK JS files.
- **Lazy discovery** — `_discover()` is now deferred until the first registry
  query instead of running eagerly in `__init__`. Uses double-checked locking for
  thread safety, preventing re-entrant recursion if a discovered module queries
  the registry at import time.

### Changed

- **`/elements` → `/refract`** — The SDK JS files are now served under `/refract/`
  instead of `/elements/`. Update any HTML `<script src>` or JS `import` paths
  accordingly (e.g. `/elements/client.js` → `/refract/client.js`).
- **PUT and PATCH use request body** — These HTTP methods now send parameters as
  a JSON request body (same as POST) rather than query string params. DELETE
  continues to use query params.

### Fixed

- **HTTPException pass-through** — `HTTPException` raised inside a registered
  function is now re-raised as-is, preserving the original status code and detail
  (404, 409, 422, etc.) instead of being wrapped as a generic 500.
- **`serve-mcp` docstring** — Corrected the CLI help text: `serve-mcp` starts a
  **MCP-only** server, not API+MCP.

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
