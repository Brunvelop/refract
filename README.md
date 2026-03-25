# refract 💎

> **One Python function. Four interfaces. Zero boilerplate.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status: Stable](https://img.shields.io/badge/status-stable-brightgreen.svg)]()

Define a typed Python function once — and automatically get a **REST API**, a **CLI**, **MCP tools** for AI agents, and a **Web UI**.

```python
from pydantic import BaseModel
from refract import Refract, register_function

class Sum(BaseModel):
    result: int

@register_function()
def add(a: int, b: int) -> Sum:
    """Add two numbers.
    Args:
        a: First number
        b: Second number
    """
    return Sum(result=a + b)

app = Refract("my-project")
```

That's it. No routers, no argument parsers, no tool definitions.

---

## What you get

| Interface | How to get it | What it gives you |
|-----------|--------------|-------------------|
| **REST API** | `app.api()` | FastAPI app with auto-generated endpoints |
| **CLI** | `app.cli()` | Click group with `serve`, `list`, and one command per function |
| **MCP tools** | `app.mcp()` | FastAPI + MCP server for AI agents / LLMs |
| **Web UI** | `<auto-add></auto-add>` | Auto-generated form card for every function |

---

## 🚀 Quick start

**Install:**

```bash
pip install git+https://github.com/Brunvelop/refract
```

**Try the demo right now:**

```bash
git clone https://github.com/Brunvelop/refract && cd refract
python demo.py serve          # API + MCP + Web UI at http://localhost:8000
python demo.py list           # List all registered functions
python demo.py add --a 3 --b 5
python demo.py greet --name World
```

---

## 🧩 Define functions

Every function follows the same pattern: **typed signature + docstring + `BaseModel` return type**.

```python
from pydantic import BaseModel
from refract import register_function

class SearchResponse(BaseModel):
    items: list[str]
    total: int

@register_function(http_methods=["GET"])
def search(query: str, limit: int = 10) -> SearchResponse:
    """Search items.
    Args:
        query: Search term
        limit: Maximum number of results
    """
    results = ["foo", "bar", "baz"][:limit]
    return SearchResponse(items=results, total=len(results))
```

The return type becomes the FastAPI `response_model` — precise OpenAPI schema, full type safety, and the exact same shape on every interface.

### Decorator options

```python
@register_function(
    http_methods=["GET", "POST"],   # default: ["GET", "POST"]
    interfaces=["api", "cli"],      # default: ["api", "cli", "mcp"]
    streaming=False,                # default: False
    stream_func=None,               # required if streaming=True
)
```

> **Note:** `async def` functions are fully supported on **API** and **MCP** interfaces — they will be properly awaited. The **CLI** interface only supports synchronous functions; async functions are automatically skipped with a warning at CLI build time.

> **CLI limitations:** Parameters with complex types (`list`, `dict`, `List[str]`, `Dict[str, int]`, etc.) fall back to plain strings in the CLI interface. Click only natively supports `int`, `float`, `bool`, and `str`. For functions that require structured inputs, consider restricting them to `interfaces=["api", "mcp"]`, or accept a JSON string and parse it inside the function.

---

## 📐 Levels of complexity

The setup scales progressively. Each level adds one or two lines — never a new file.

### Level 1 — One line (recommended default)

```python
# my_project/app.py
from refract import Refract

app = Refract("my-project", discover=["my_project.core"])
```

Wire it up as a CLI entry point:

```toml
# pyproject.toml
[project.scripts]
my-project = "my_project.app:app.run_cli"
```

You immediately get:

```bash
my-project serve          # Start unified server (API + MCP + UI) at http://0.0.0.0:8000
my-project serve-api      # Start REST API only at http://127.0.0.1:8000
my-project serve-mcp      # Start API + MCP at http://127.0.0.1:8001
my-project list           # List all registered functions
my-project add --a 1 --b 2   # Call any registered function directly
my-project --verbose serve   # Enable DEBUG logging
```

> **No boilerplate.** The `discover=` list tells Refract which packages to scan for `@register_function` decorators. Everything else is automatic.

> **Advanced uvicorn options** — The built-in `serve` commands are convenience wrappers that support `--host` and `--port`. Features like auto-reload, multiple workers, or custom log levels require uvicorn to be invoked with a **string import path** pointing to an ASGI application. `app.run_cli` is a Click group, not an ASGI app — expose `app.api()` as a module-level variable instead:
>
> ```python
> # my_project/app.py
> from refract import Refract
>
> app = Refract("my-project", discover=["my_project.core"])
> fastapi_app = app.api()  # ASGI app — this is what uvicorn needs
> ```
>
> ```bash
> # Auto-reload in development
> uvicorn my_project.app:fastapi_app --reload
>
> # Multiple workers for production
> uvicorn my_project.app:fastapi_app --workers 4 --host 0.0.0.0 --port 8000
>
> # Custom log level
> uvicorn my_project.app:fastapi_app --log-level warning
> ```
>
> See the [uvicorn docs](https://www.uvicorn.org/settings/) for the full list of available options.

### Level 2 — Custom CLI commands

Same file, add `@app.command()`:

```python
# my_project/app.py
from refract import Refract

app = Refract("my-project", discover=["my_project.core"])

@app.command()
def health_check():
    """Run project health checks."""
    import subprocess
    subprocess.run(["pytest", "tests/health/", "-q"])
```

```bash
my-project health-check   # Your custom command, alongside serve/list
```

Custom commands use Click under the hood — `click.echo`, `click.option`, etc. work normally.

### Level 3 — Bring your own FastAPI app

Use `app.router()` to mount only the function endpoints onto your own FastAPI instance:

```python
# my_project/app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from refract import Refract

refract_app = Refract("my-project", discover=["my_project.core"])

my_app = FastAPI(title="My Project", version="1.0.0")
my_app.add_middleware(CORSMiddleware, allow_origins=["*"])
my_app.include_router(refract_app.router())

@my_app.get("/status")
def status():
    return {"ok": True}
```

`app.router()` includes:
- `POST/GET /{funcName}` — one endpoint per registered function
- `GET /functions/details` — JSON Schema discovery for the frontend
- `GET /health` — basic health check

---

## 📡 Streaming (SSE)

For long-running functions (LLM calls, background jobs), use Server-Sent Events:

```python
import json
import asyncio
from pydantic import BaseModel
from refract import register_function
from refract.sse import format_sse

class ProcessResult(BaseModel):
    text: str

async def _stream_process(text: str):
    """Async generator that yields SSE-formatted events."""
    words = text.split()
    for word in words:
        await asyncio.sleep(0.1)
        yield format_sse("token", json.dumps({"chunk": word}))
    yield format_sse("complete", json.dumps({"message": "done"}))

@register_function(streaming=True, stream_func=_stream_process)
def process_text(text: str) -> ProcessResult:
    """Process text word by word.
    Args:
        text: Text to process
    """
    return ProcessResult(text=text)
```

On the frontend, consume it with `RefractClient.stream()`:

```javascript
import { RefractClient } from '/elements/client.js';
const api = new RefractClient();

for await (const { event, data } of api.stream('process_text', { text: 'hello world' })) {
    if (event === 'token') console.log(data.chunk);
    if (event === 'complete') console.log('Done:', data.message);
}
```

---

## 🌐 Frontend

Three layers — use as much or as little as you need.

> **Note:** The Web UI components (Layers 2 & 3) import
> [Lit](https://lit.dev/) from `cdn.jsdelivr.net` at runtime.
> An internet connection is required. For air-gapped environments,
> bundle Lit locally and update the import paths in `controller.js`
> and `element.js`.

### Layer 1: `RefractClient` (vanilla JS, no framework)

Pure HTTP client. Works anywhere — Lit components, vanilla JS, tests.

```html
<script type="module">
import { RefractClient } from '/elements/client.js';

const api = new RefractClient();
await api.loadSchemas();

const result = await api.call('add', { a: 1, b: 2 });
console.log(result); // { result: 3 }

const schema = api.getSchema('add');
console.log(schema.parameters);
// [{ name: 'a', type: 'int', required: true, ... }, ...]
</script>
```

### Layer 2: `AutoFunctionController` (Lit, stateful)

LitElement with state management, validation, and execution lifecycle. Extend it to build custom function UIs.

```html
<script type="module">
import { AutoFunctionController } from '/elements/controller.js';

class MyFunctionUI extends AutoFunctionController {
    render() {
        return html`
            <input @change=${e => this.setParam('a', e.target.value)} />
            <button @click=${this.execute}>Run</button>
            ${this.result ? html`<pre>${JSON.stringify(this.result)}</pre>` : ''}
        `;
    }
}

customElements.define('my-function-ui', MyFunctionUI);
</script>

<my-function-ui func-name="add"></my-function-ui>
```

Lifecycle events: `before-execute`, `after-execute`, `execute-error`, `function-connected`, `params-changed`.

```javascript
// Static helper — no DOM element needed
const result = await AutoFunctionController.executeFunction('add', { a: 1, b: 2 });
```

### Layer 3: `AutoFunctionElement` (Lit, visual card)

Ready-to-use card UI. Auto-generates form fields from the schema — no configuration.

```html
<script type="module" src="/elements/element.js"></script>
<auto-function-element func-name="add"></auto-function-element>
```

Renders: function name + description, typed inputs (text, number, checkbox, select for `Literal` types, textarea for `dict`/`list`), execute button, result display.

### Zero-config: `AutoElementGenerator`

Auto-fetches `/functions/details` and registers `<auto-{funcName}>` for every function:

```html
<!-- Load once — registers <auto-add>, <auto-search>, etc. automatically -->
<script type="module" src="/elements/generator.js"></script>

<auto-add></auto-add>
<auto-search></auto-search>
```

---

## 🔗 Schema sharing (back ↔ front)

Every function schema includes a `response_schema` — the JSON Schema generated by Pydantic from the return type. This is the contract between backend and frontend.

```
GET /functions/details
```

```json
{
  "functions": {
    "add": {
      "name": "add",
      "description": "Add two numbers.",
      "http_methods": ["GET", "POST"],
      "parameters": [
        { "name": "a", "type": "int", "required": true, "description": "First number" },
        { "name": "b", "type": "int", "required": true, "description": "Second number" }
      ],
      "streaming": false,
      "response_schema": {
        "properties": {
          "result": { "title": "Result", "type": "integer" }
        },
        "required": ["result"],
        "title": "Sum",
        "type": "object"
      }
    }
  }
}
```

The frontend always knows the exact shape of the response — enabling runtime validation, type-safe consumers, and future codegen.

---

## 🔍 Discovery logging

When `Refract` scans your packages, you see exactly what happened:

```
[refract:my-project] Scanning my_project.core...
[refract:my-project]   ✅ my_project.core.math — 2 functions
[refract:my-project]   ✅ my_project.core.search — 1 function
[refract:my-project]   ⚠️  my_project.core.ai — skipped (ImportError: dspy not installed)
[refract:my-project]   ℹ️  my_project.core.models — no @register_function found
[refract:my-project] Total: 3 functions registered, 1 module skipped
```

Use `--verbose` to enable DEBUG-level output, or pass `strict=True` to `_discover()` to raise on import errors.

---

## 🏗 Architecture

```
refract/
├── refract/
│   ├── __init__.py       # Public API: Refract, register_function (version falls back to `0.0.0-dev` when not installed)
│   ├── models.py         # ParamSchema, FunctionInfo, FunctionSchema
│   ├── registry.py       # @register_function decorator + Registry class
│   ├── refract.py        # Refract facade class
│   ├── api.py            # FastAPI app/router factories
│   ├── cli.py            # Click group factory
│   ├── mcp.py            # FastAPI + MCP factory
│   ├── sse.py            # format_sse(), _create_stream_handler()
│   ├── log_config.py     # configure_cli_logging(), configure_api_logging()
│   └── web/
│       ├── client.js     # RefractClient — Layer 1 (vanilla JS)
│       ├── controller.js # AutoFunctionController — Layer 2 (Lit)
│       ├── element.js    # AutoFunctionElement — Layer 3 (Lit card UI)
│       ├── generator.js  # AutoElementGenerator — zero-config custom elements
│       └── views/
│           └── dashboard.html  # Default web UI (served at / and /functions)
├── demo.py               # Runnable demo — try it right now
└── tests/
    ├── conftest.py
    ├── test_models.py
    ├── test_registry.py
    ├── test_api.py
    ├── test_cli.py
    ├── test_mcp.py
    └── test_sse.py
```

---

## 📖 API Reference

### `Refract(name, discover=None)`

| Method / Property | Returns | Description |
|---|---|---|
| `.api()` | `FastAPI` | Complete FastAPI app with static files and HTML views |
| `.router()` | `APIRouter` | Only the function endpoints (mount in your own app) |
| `.cli()` | `click.Group` | Click group with built-in and function commands |
| `.mcp()` | `FastAPI` | FastAPI app with MCP integration |
| `.mcp_only()` | `FastAPI` | MCP-only FastAPI app (no REST API endpoints) |
| `.run_cli` | `click.Group` | Cached property — use as `pyproject.toml` entry point |
| `@.command()` | decorator | Register a custom Click command on this instance |
| `.get_all_functions()` | `list[FunctionInfo]` | All registered functions |
| `.get_all_schemas()` | `list[FunctionSchema]` | Serialisable schemas (JSON-safe) |
| `.get_function_by_name(name)` | `FunctionInfo \| None` | Look up a function by name |
| `.function_count()` | `int` | Number of registered functions |

### `register_function(...)`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `http_methods` | `list[str]` | `["GET", "POST"]` | HTTP verbs to expose on the API |
| `interfaces` | `list[str]` | `["api", "cli", "mcp"]` | Which interfaces to enable |
| `streaming` | `bool` | `False` | Enable SSE streaming mode |
| `stream_func` | `Callable \| None` | `None` | Async generator for streaming (required if `streaming=True`) |

### `format_sse(event, data)`

```python
from refract.sse import format_sse

line = format_sse("token", '{"chunk": "hello"}')
# → "event: token\ndata: {\"chunk\": \"hello\"}\n\n"
```

---

## License

MIT — see [LICENSE](LICENSE).
