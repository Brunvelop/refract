"""
SSE (Server-Sent Events) utilities for Refract streaming endpoints.

This module provides generic SSE helpers that can be used with any async
generator — no DSPy or LLM-specific logic here. The consumers (e.g. autocode)
only need to provide an async generator; Refract handles the HTTP transport.

Usage::

    from refract.sse import format_sse, _create_stream_handler

    # format_sse: build a raw SSE line from event + JSON data
    line = format_sse("token", '{"chunk": "hello"}')
    # → "event: token\\ndata: {\"chunk\": \"hello\"}\\n\\n"

    # _create_stream_handler: create a FastAPI handler for SSE streaming
    handler = _create_stream_handler(my_stream_func, DynamicModel)
"""

__all__ = ["format_sse"]

from fastapi.responses import StreamingResponse


def format_sse(event: str, data: str) -> str:
    """Format a single Server-Sent Event message.

    Args:
        event: The SSE event type (e.g. ``"token"``, ``"complete"``, ``"error"``).
        data: The event payload — typically a JSON-serialised string.

    Returns:
        A complete SSE message ready to be yielded by a streaming response,
        including the trailing double newline that marks the end of the event.

    Example::

        import json
        line = format_sse("token", json.dumps({"chunk": "hello"}))
        # "event: token\\ndata: {\\"chunk\\": \\"hello\\"}\\n\\n"
    """
    return f"event: {event}\ndata: {data}\n\n"


def _create_stream_handler(stream_func, DynamicModel):
    """Create a FastAPI SSE streaming handler.

    Decoupled from model creation so that ``api.py`` can call
    ``_create_dynamic_model`` first and pass the result here, avoiding
    a circular import between ``sse.py`` and ``api.py``.

    Args:
        stream_func: Async generator callable that accepts ``**kwargs`` and
            yields SSE-formatted strings (use ``format_sse`` to build them).
        DynamicModel: A Pydantic model class (created by ``_create_dynamic_model``)
            that FastAPI uses to parse and validate the request body.

    Returns:
        An ``async def handler(request: DynamicModel)`` coroutine that returns
        a ``StreamingResponse`` with the standard SSE headers.

    Example::

        DynamicModel = _create_dynamic_model(func_info, for_post=True)
        handler = _create_stream_handler(my_gen, DynamicModel)
        app.add_api_route("/my_fn", handler, methods=["POST"])
    """
    async def handler(request: DynamicModel):
        params = request.model_dump()
        return StreamingResponse(
            stream_func(**params),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return handler
