# refract 🔻

> Refract a Python function into multiple interfaces: REST API, CLI, MCP tools, and Web UI.

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

## What you get

| Interface | How |
|-----------|-----|
| REST API  | `app.api()` → FastAPI app |
| CLI       | `app.cli()` → Click group |
| MCP tools | `app.mcp()` → FastAPI + MCP server |
| Web UI    | Auto-generated form for every function |

## Install

```bash
pip install git+https://github.com/Brunvelop/refract
```

## Quick start

```python
# my_project/app.py
from refract import Refract

app = Refract("my-project", discover=["my_project.core"])
```

```toml
# pyproject.toml
[project.scripts]
my-project = "my_project.app:app.run_cli"
```

```bash
my-project serve       # API + MCP at http://localhost:8000
my-project list        # Show registered functions
```

## Levels of complexity

### Level 1 — One line (default for most projects)

```python
app = Refract("my-project", discover=["my_project.core"])
```

### Level 2 — Custom CLI commands

```python
app = Refract("my-project", discover=["my_project.core"])

@app.command()
def my_custom_command():
    """Run something custom."""
    ...
```

### Level 3 — Bring your own FastAPI app

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from refract import Refract

refract_app = Refract("my-project", discover=["my_project.core"])

my_app = FastAPI()
my_app.add_middleware(CORSMiddleware, allow_origins=["*"])
my_app.include_router(refract_app.router())  # only the function endpoints
```

## Frontend

```html
<!-- Auto-generate a UI card for every registered function -->
<script type="module" src="/elements/generator.js"></script>
<auto-add></auto-add>

<!-- Or use RefractClient directly for custom UIs -->
<script type="module">
import { RefractClient } from '/elements/client.js';
const api = new RefractClient();
await api.loadSchemas();
const result = await api.call('add', { a: 1, b: 2 });
</script>
```

## License

MIT
