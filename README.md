# refract 🔻

> Refract a Python function into multiple interfaces: REST API, CLI, MCP tools, and Web UI — automatically.

```python
from refract import Refract, register_function, GenericOutput

@register_function()
def add(a: int, b: int) -> GenericOutput:
    """Add two numbers.
    Args:
        a: First number
        b: Second number
    """
    return GenericOutput(result=a + b)

app = Refract("my-project", discover=["my_project.core"])
```

One function definition. Four interfaces for free.

---

## What you get

| Interface | How to get it | What it gives you |
|-----------|--------------|-------------------|
| **REST API** | `app.api()` | FastAPI app with auto-generated endpoints |
| **CLI** | `app.cli()` | Click group with `serve`, `list`, and one command per function |
| **MCP tools** | `app.mcp()` | FastAPI + MCP server for AI agents / LLMs |
| **Web UI** | `<auto-add></auto-add>` | Auto-generated form card for every function |

---

## Install

```bash
pip install git+https://github.com/Brunvelop/refract
```

---

## Define functions

### Convenience output: `GenericOutput`

The simplest way to expose a function — `GenericOutput` wraps any value with a standard envelope:

```python
from refract import register_function, GenericOutput

@register_function()
def add(a: int, b: int) -> GenericOutput:
    """Add two numbers.
    Args:
        a: First number
        b: Second number
    """
    return GenericOutput(result=a + b)
```

`GenericOutput` has three fields: `result: Any`, `success: bool`, `message: str | None`.

### Typed output: any `BaseModel`

For richer OpenAPI schemas and strong typing, return your own Pydantic model instead:

```python
from pydantic import BaseModel
from refract import register_function

class SearchResponse(BaseModel):
    items: list[str]
    total: int

@register_function(http_methods=["GET"])
def search(query: str) -> SearchResponse:
    """Search items.
    Args:
        query: Search term
    """
    results = ["foo", "bar"]
    return SearchResponse(items=results, total=len(results))
```

The return type becomes the FastAPI `response_model` → precise OpenAPI schema, no `result: Any` everywhere.

### Decorator options

```python
@register_function(
    http_methods=["GET", "POST"],   # default: ["GET", "POST"]
    interfaces=["api", "cli"],      # default: ["api", "cli", "mcp"]
    streaming=False,                # default: False
    stream_func=None,               # required if streaming=True
)
```

---

## Levels of complexity

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
my-project serve          # Start unified server (API + MCP) at http://0.0.0.0:8000
my-project serve-api      # Start REST API only at http://127.0.0.1:8000
my-project serve-mcp      # Start API + MCP at http://127.0.0.1:8001
my-project list           # List all registered functions
my-project add --a 1 --b 2   # Call any registered function directly
my-project --verbose serve   # Enable DEBUG logging
```

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

Custom commands use Click under the hood — you can use `click.echo`, `click.option`, etc. normally.

### Level 3 — Bring your own FastAPI app

Use `app.router()` to mount only the function endpoints onto your own FastAPI instance:

```python
# my_project/app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from refract import Refract

refract_app = Refract("my-project", discover=["my_project.core"])

# Your own FastAPI with full control
my_app = FastAPI(title="My Project", version="1.0.0")
my_app.add_middleware(CORSMiddleware, allow_origins=["*"])

# Mount only the dynamic function endpoints
my_app.include_router(refract_app.router())

# Add your own custom endpoints alongside
@my_app.get("/status")
def status():
    return {"ok": True}
```

`app.router()` includes:
- `POST/GET /{funcName}` — one endpoint per registered function
- `GET /functions/details` — JSON Schema discovery for the frontend
- `GET /health` — basic health check

---

## Streaming (SSE)

For long-running functions (LLM calls, background jobs), use Server-Sent Events:

```python
# my_project/core/ai.py
import json
import asyncio
from refract import register_function, GenericOutput
from refract.sse import format_sse

async def _stream_process(text: str):
    """Async generator that yields SSE-formatted events."""
    words = text.split()
    for word in words:
        await asyncio.sleep(0.1)
        yield format_sse("token", json.dumps({"chunk": word}))
    yield format_sse("complete", json.dumps({"message": "done"}))

@register_function(streaming=True, stream_func=_stream_process)
def process_text(text: str) -> GenericOutput:
    """Process text word by word.
    Args:
        text: Text to process
    """
    return GenericOutput(result=text)
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

## Frontend

Three layers — use as much or as little as you need.

### Layer 1: `RefractClient` (vanilla JS, no Lit)

Pure HTTP client. No framework dependency. Works anywhere — Lit components, vanilla JS, tests.

```html
<script type="module">
import { RefractClient } from '/elements/client.js';

const api = new RefractClient();

// Load all function schemas from /functions/details (cached)
await api.loadSchemas();

// Call any registered function
const result = await api.call('add', { a: 1, b: 2 });
console.log(result); // { result: 3, success: true, message: null }

// Get a specific function's schema
const schema = api.getSchema('add');
console.log(schema.parameters); // [{ name: 'a', type: 'int', required: true, ... }, ...]
</script>
```

### Layer 2: `AutoFunctionController` (Lit, stateful)

LitElement with state management, validation, and execution lifecycle. Extend this to build custom function UIs.

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

Controller lifecycle events: `before-execute`, `after-execute`, `execute-error`, `function-connected`, `params-changed`.

Static helper for calling functions without a DOM element:

```javascript
const result = await AutoFunctionController.executeFunction('add', { a: 1, b: 2 });
```

### Layer 3: `AutoFunctionElement` (Lit, visual card)

Ready-to-use card UI. Auto-generates form fields from the function schema — no configuration needed.

```html
<script type="module" src="/elements/element.js"></script>
<auto-function-element func-name="add"></auto-function-element>
```

Renders a card with: function name, description, typed inputs (text, number, checkbox, select for `Literal` types, textarea for `dict`/`list`), execute button, and result display.

### Zero-config: `AutoElementGenerator`

Auto-fetches `/functions/details` on load and registers `<auto-{funcName}>` for every function:

```html
<!-- Load once — registers <auto-add>, <auto-search>, etc. automatically -->
<script type="module" src="/elements/generator.js"></script>

<!-- Use any registered function directly by name -->
<auto-add></auto-add>
<auto-search></auto-search>
```

No JavaScript required beyond the script tag.

---

## Schema sharing (back ↔ front)

Every function schema includes `response_schema` — the JSON Schema generated by Pydantic from the return type:

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
          "result": { "title": "Result" },
          "success": { "default": true, "title": "Success", "type": "boolean" },
          "message": { "anyOf": [{"type": "string"}, {"type": "null"}], "default": null }
        },
        "title": "GenericOutput",
        "type": "object"
      }
    }
  }
}
```

This means the frontend always knows the exact shape of the response — enabling runtime validation, type-safe consumers, and future codegen.

---

## Discovery logging

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

## Architecture

```
refract/
├── refract/
│   ├── __init__.py       # Public API: Refract, register_function, GenericOutput, ...
│   ├── models.py         # ParamSchema, FunctionInfo, FunctionSchema, GenericOutput
│   ├── registry.py       # @register_function decorator + Refract class
│   ├── api.py            # FastAPI app/router factories
│   ├── cli.py            # Click group factory
│   ├── mcp.py            # FastAPI + MCP factory
│   ├── sse.py            # format_sse(), _create_stream_handler()
│   ├── logging.py        # configure_cli_logging(), configure_api_logging()
│   └── web/
│       ├── client.js     # RefractClient — Layer 1 (vanilla JS)
│       ├── controller.js # AutoFunctionController — Layer 2 (Lit)
│       ├── element.js    # AutoFunctionElement — Layer 3 (Lit card UI)
│       ├── generator.js  # AutoElementGenerator — zero-config custom elements
│       └── views/
│           └── functions.html  # Default web UI page (served at / and /functions)
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

## API reference

### `Refract(name, discover=None)`

| Method / Property | Returns | Description |
|---|---|---|
| `.api()` | `FastAPI` | Complete FastAPI app with static files and HTML views |
| `.router()` | `APIRouter` | Only the function endpoints (mount in your own app) |
| `.cli()` | `click.Group` | Click group with built-in and function commands |
| `.mcp()` | `FastAPI` | FastAPI app with MCP integration |
| `.run_cli` | `click.Group` | Property alias for use in `pyproject.toml` entry points |
| `@.command()` | decorator | Register a custom Click command on this instance |
| `.get_all_functions()` | `list[FunctionInfo]` | All registered functions |
| `.get_all_schemas()` | `list[FunctionSchema]` | Serialisable schemas (JSON-safe) |
| `.get_function_by_name(name)` | `FunctionInfo \| None` | Look up a function by name |
| `.function_count()` | `int` | Number of registered functions |

### `register_function(http_methods, interfaces, streaming, stream_func)`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `http_methods` | `list[str]` | `["GET", "POST"]` | HTTP verbs to expose on the API |
| `interfaces` | `list[str]` | `["api", "cli", "mcp"]` | Which interfaces to enable |
| `streaming` | `bool` | `False` | Enable SSE streaming mode |
| `stream_func` | `Callable \| None` | `None` | Async generator for streaming (required if `streaming=True`) |

### `GenericOutput`

```python
class GenericOutput(BaseModel):
    result: Any          # The return value
    success: bool = True # Whether the operation succeeded
    message: str | None  # Optional human-readable message
```

### `format_sse(event, data)`

```python
from refract.sse import format_sse

line = format_sse("token", '{"chunk": "hello"}')
# → "event: token\ndata: {\"chunk\": \"hello\"}\n\n"
```

---

## License

MIT — see [LICENSE](LICENSE).
