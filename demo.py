"""
Demo — Refract in action.

Usage:
    python demo.py serve          # API + MCP + UI at http://localhost:8000
    python demo.py serve-api      # REST API only
    python demo.py list           # List registered functions
    python demo.py add --a 3 --b 5
    python demo.py greet --name World
"""
from pydantic import BaseModel
from refract import Refract, register_function


class Sum(BaseModel):
    result: int

class Greeting(BaseModel):
    message: str


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
    """Greet a person.
    Args:
        name: Name of the person
        greeting: Greeting word
    """
    return Greeting(message=f"{greeting}, {name}!")


app = Refract("demo")

if __name__ == "__main__":
    app.run_cli()
