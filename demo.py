"""
Demo — Refract in action.

Showcases all decorator features (backend) and all 3 frontend layers.

Usage:
    python demo.py serve          # API + MCP + Web UI at http://localhost:8000
    python demo.py serve-api      # REST API only
    python demo.py list           # List registered functions
    python demo.py add --a 3 --b 5
    python demo.py greet --name World
    python demo.py search --query python
    python demo.py bmi --weight-kg 70 --height-m 1.75

    # Or run the full demo directly (recommended for dev):
    uvicorn demo:fastapi_app --reload
"""
import asyncio
import json
import os
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from refract import Refract, register_function
from refract.sse import format_sse


# ── Response models ──────────────────────────────────────────────────────────

class Sum(BaseModel):
    result: int

class Greeting(BaseModel):
    message: str

class SearchResult(BaseModel):
    items: list[str]
    total: int
    category: str

class BmiResult(BaseModel):
    bmi: float
    category: str

class Summary(BaseModel):
    summary: str
    words: int

class StreamResult(BaseModel):
    text: str


# ── Functions ────────────────────────────────────────────────────────────────

@register_function()
def add(a: int, b: int) -> Sum:
    """Add two numbers.
    Args:
        a: First number
        b: Second number
    """
    return Sum(result=a + b)


@register_function()
def greet(name: str, greeting: str = "Hello") -> Greeting:
    """Greet someone with a custom message.
    Args:
        name: Name of the person
        greeting: Greeting word
    """
    return Greeting(message=f"{greeting}, {name}!")


@register_function(http_methods=["GET"])
def search(query: str, category: Literal["all", "docs", "code", "people"] = "all", limit: int = 5) -> SearchResult:
    """Search items. Uses GET only, Literal param becomes a select in the UI.
    Args:
        query: Search term
        category: Filter by category
        limit: Max results to return
    """
    items = [f"{query} result #{i+1} [{category}]" for i in range(limit)]
    return SearchResult(items=items, total=len(items), category=category)


@register_function()
def bmi(weight_kg: float, height_m: float, metric: bool = True) -> BmiResult:
    """Calculate Body Mass Index (BMI). Demonstrates float and bool params.
    Args:
        weight_kg: Weight in kilograms
        height_m: Height in meters
        metric: Use metric units (always True in this demo)
    """
    value = round(weight_kg / (height_m ** 2), 1)
    if value < 18.5:
        cat = "Underweight"
    elif value < 25:
        cat = "Normal"
    elif value < 30:
        cat = "Overweight"
    else:
        cat = "Obese"
    return BmiResult(bmi=value, category=cat)


@register_function(interfaces=["api", "mcp"])
async def summarize(text: str, max_words: int = 20) -> Summary:
    """Summarize text. Async function — exposed on API and MCP only (no CLI).
    Args:
        text: Text to summarize
        max_words: Maximum words in the summary
    """
    await asyncio.sleep(0.01)  # simulate async work
    words = text.split()[:max_words]
    return Summary(summary=" ".join(words) + ("…" if len(text.split()) > max_words else ""), words=len(words))


async def _stream_words(text: str, delay: float = 0.15):
    """Yields each word as an SSE token event, then a complete event."""
    for word in text.split():
        await asyncio.sleep(delay)
        yield format_sse("token", json.dumps({"chunk": word}))
    yield format_sse("complete", json.dumps({"message": "done"}))


@register_function(streaming=True, stream_func=_stream_words)
def stream_words(text: str, delay: float = 0.15) -> StreamResult:
    """Stream text word by word via SSE. Demonstrates the streaming interface.
    Args:
        text: Text whose words will be streamed one by one
        delay: Seconds between each word
    """
    return StreamResult(text=text)


# ── App ──────────────────────────────────────────────────────────────────────
# Level 3: bring-your-own FastAPI.
# app.router() gives us only the function endpoints (no HTML pages).
# We control all routes:
#   /             → demo.html  (frontend layers demo)
#   /dashboard    → dashboard.html  (refract auto-UI)
#   /elements/*   → refract web components (static JS)

app = Refract("demo")

_root = os.path.dirname(os.path.abspath(__file__))
_web_dir = os.path.join(_root, "refract", "web")
_dashboard_html = os.path.join(_web_dir, "views", "dashboard.html")
_demo_html = os.path.join(_root, "demo.html")

fastapi_app = FastAPI(title="Refract Demo", description="All features, one file.")
fastapi_app.include_router(app.router())
fastapi_app.mount("/elements", StaticFiles(directory=_web_dir), name="elements")


@fastapi_app.get("/")
async def demo_page():
    """Frontend layers demo — zero-config, Layer 3, Layer 2, Layer 1, SSE."""
    return FileResponse(_demo_html)


@fastapi_app.get("/dashboard")
async def dashboard():
    """Refract auto-generated UI — registry overview + interactive cards."""
    return FileResponse(_dashboard_html)


@app.command()
def open_demo():
    """Open the frontend demo page in the browser."""
    import webbrowser
    webbrowser.open("http://localhost:8000")
    print("→ http://localhost:8000")


if __name__ == "__main__":
    app.run_cli()
