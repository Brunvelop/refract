"""
Tests for refract.sse module.

Tests the generic Server-Sent Events utilities: format_sse() helper
and _create_stream_handler() FastAPI handler factory.
"""
import pytest
import asyncio
import json
from unittest.mock import Mock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, create_model

from refract.sse import format_sse, _create_stream_handler


# ---------------------------------------------------------------------------
# Tests: format_sse
# ---------------------------------------------------------------------------

class TestFormatSse:
    """Tests for format_sse — SSE message formatting."""

    def test_format_sse_basic(self):
        """format_sse produces a correctly formatted SSE message."""
        result = format_sse("token", '{"chunk": "hello"}')

        assert result == 'event: token\ndata: {"chunk": "hello"}\n\n'

    def test_format_sse_ends_with_double_newline(self):
        """SSE messages must end with a double newline."""
        result = format_sse("complete", '{"success": true}')

        assert result.endswith("\n\n")

    def test_format_sse_contains_event_prefix(self):
        """Result contains the 'event: <name>' line."""
        result = format_sse("error", '{"message": "oops"}')

        assert "event: error\n" in result

    def test_format_sse_contains_data_prefix(self):
        """Result contains the 'data: <payload>' line."""
        payload = '{"status": "ok"}'
        result = format_sse("status", payload)

        assert f"data: {payload}\n" in result

    def test_format_sse_with_json_payload(self):
        """format_sse works correctly with a serialised JSON payload."""
        payload = json.dumps({"chunk": "world", "index": 3})
        result = format_sse("token", payload)

        # Parse back the data line
        lines = result.strip().split("\n")
        event_line = next(l for l in lines if l.startswith("event:"))
        data_line = next(l for l in lines if l.startswith("data:"))

        assert event_line == "event: token"
        data_value = data_line[len("data: "):]
        parsed = json.loads(data_value)
        assert parsed["chunk"] == "world"
        assert parsed["index"] == 3

    def test_format_sse_various_event_types(self):
        """format_sse works with any event type string."""
        for event in ["token", "complete", "error", "status", "ping", "custom_event"]:
            result = format_sse(event, '{}')
            assert f"event: {event}\n" in result

    def test_format_sse_empty_data(self):
        """format_sse accepts an empty data string."""
        result = format_sse("ping", "")

        assert result == "event: ping\ndata: \n\n"

    def test_format_sse_structure(self):
        """Verify exact byte-level structure of a SSE message."""
        result = format_sse("ev", "d")
        assert result == "event: ev\ndata: d\n\n"


# ---------------------------------------------------------------------------
# Tests: _create_stream_handler
# ---------------------------------------------------------------------------

class TestCreateStreamHandler:
    """Tests for _create_stream_handler — FastAPI SSE handler factory."""

    def _make_model(self, **field_defs):
        """Helper to create a simple Pydantic model for testing."""
        return create_model("TestInput", **field_defs)

    def test_returns_callable(self):
        """_create_stream_handler returns a callable."""
        async def noop(**kw):
            yield ""

        DynamicModel = self._make_model()
        handler = _create_stream_handler(noop, DynamicModel)

        assert callable(handler)

    def test_handler_is_async(self):
        """The returned handler is an async function."""
        async def noop(**kw):
            yield ""

        DynamicModel = self._make_model()
        handler = _create_stream_handler(noop, DynamicModel)

        assert asyncio.iscoroutinefunction(handler)

    def test_handler_returns_streaming_response(self):
        """The handler returns a StreamingResponse instance."""
        async def mock_gen(**kw):
            yield format_sse("token", '{"chunk": "hi"}')
            yield format_sse("complete", '{"success": true}')

        DynamicModel = self._make_model()
        handler = _create_stream_handler(mock_gen, DynamicModel)

        request = DynamicModel()
        result = asyncio.run(handler(request))

        assert isinstance(result, StreamingResponse)

    def test_handler_media_type_is_sse(self):
        """StreamingResponse has media_type='text/event-stream'."""
        async def noop(**kw):
            yield ""

        DynamicModel = self._make_model()
        handler = _create_stream_handler(noop, DynamicModel)

        request = DynamicModel()
        result = asyncio.run(handler(request))

        assert result.media_type == "text/event-stream"

    def test_handler_has_correct_headers(self):
        """StreamingResponse includes Cache-Control, Connection, X-Accel-Buffering headers."""
        async def noop(**kw):
            yield ""

        DynamicModel = self._make_model()
        handler = _create_stream_handler(noop, DynamicModel)

        request = DynamicModel()
        result = asyncio.run(handler(request))

        assert result.headers.get("Cache-Control") == "no-cache"
        assert result.headers.get("Connection") == "keep-alive"
        assert result.headers.get("X-Accel-Buffering") == "no"

    def test_handler_passes_params_to_stream_func(self):
        """Handler extracts request fields and passes them as kwargs to the generator."""
        received = {}

        async def capture_gen(**kw):
            received.update(kw)
            yield format_sse("complete", "{}")

        DynamicModel = self._make_model(
            message=(str, ...),
            temperature=(float, 0.7),
        )
        handler = _create_stream_handler(capture_gen, DynamicModel)

        request = DynamicModel(message="hello", temperature=0.9)
        result = asyncio.run(handler(request))

        # Consume the async generator to trigger capture
        async def consume():
            async for _ in result.body_iterator:
                pass
        asyncio.run(consume())

        assert received["message"] == "hello"
        assert received["temperature"] == 0.9

    def test_handler_with_no_params(self):
        """Handler works when the function takes no parameters."""
        produced = []

        async def no_param_gen(**kw):
            yield format_sse("token", '{"chunk": "a"}')
            yield format_sse("complete", '{"success": true}')

        DynamicModel = self._make_model()
        handler = _create_stream_handler(no_param_gen, DynamicModel)

        request = DynamicModel()
        result = asyncio.run(handler(request))

        async def collect():
            async for chunk in result.body_iterator:
                produced.append(chunk)
        asyncio.run(collect())

        assert len(produced) == 2
        assert "token" in produced[0]
        assert "complete" in produced[1]

    def test_handler_streams_multiple_events(self):
        """All events yielded by the generator are delivered to the client."""
        events = [
            format_sse("token", '{"chunk": "a"}'),
            format_sse("token", '{"chunk": "b"}'),
            format_sse("token", '{"chunk": "c"}'),
            format_sse("complete", '{"success": true}'),
        ]

        async def multi_event_gen(**kw):
            for ev in events:
                yield ev

        DynamicModel = self._make_model()
        handler = _create_stream_handler(multi_event_gen, DynamicModel)

        request = DynamicModel()
        response = asyncio.run(handler(request))

        collected = []
        async def collect():
            async for chunk in response.body_iterator:
                collected.append(chunk)
        asyncio.run(collect())

        assert len(collected) == 4
        assert collected == events

    def test_handler_integration_with_fastapi(self):
        """Handler can be registered in a real FastAPI app and serve SSE requests."""
        async def stream_gen(**kw):
            yield format_sse("token", '{"chunk": "hello"}')
            yield format_sse("complete", '{"success": true}')

        DynamicModel = self._make_model(message=(str, "default"))
        handler = _create_stream_handler(stream_gen, DynamicModel)

        app = FastAPI()
        app.add_api_route("/stream", handler, methods=["POST"])
        client = TestClient(app)

        response = client.post("/stream", json={"message": "test"})

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        content = response.text
        assert "event: token" in content
        assert "event: complete" in content


# ---------------------------------------------------------------------------
# Tests: format_sse + _create_stream_handler integration
# ---------------------------------------------------------------------------

class TestSseIntegration:
    """Integration tests combining format_sse and _create_stream_handler."""

    def test_round_trip_sse_events(self):
        """Events formatted with format_sse are correctly consumed by the handler."""
        messages = ["Hello", "World", "!"]
        produced_events = [
            format_sse("token", json.dumps({"chunk": m})) for m in messages
        ] + [format_sse("complete", json.dumps({"success": True}))]

        async def my_stream(**kw):
            for ev in produced_events:
                yield ev

        DynamicModel = create_model("Input")
        handler = _create_stream_handler(my_stream, DynamicModel)

        app = FastAPI()
        app.add_api_route("/chat", handler, methods=["POST"])
        client = TestClient(app)

        response = client.post("/chat", json={})
        assert response.status_code == 200

        content = response.text
        # All token events should be present
        for msg in messages:
            assert msg in content
        assert "complete" in content
        assert '"success": true' in content.lower() or '"success":true' in content.lower()
