"""local_detect: probe fake Ollama / LM Studio servers, handle failures, grade quality."""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.core.llm import local_detect


class _Handler(BaseHTTPRequestHandler):
    routes: dict[str, tuple[int, bytes]] = {}

    def do_GET(self):  # noqa: N802 - http.server API
        status, body = self.routes.get(self.path, (404, b"{}"))
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence test output
        pass


@pytest.fixture
def server():
    """Yields (base_url, routes) for a local HTTP server; set routes before calling detect."""
    _Handler.routes = {}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}", _Handler.routes
    finally:
        srv.shutdown()
        srv.server_close()


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_ollama_lists_models_with_sizes(server):
    base, routes = server
    routes["/api/tags"] = (
        200,
        json.dumps(
            {
                "models": [
                    {"name": "qwen2.5:14b", "details": {"parameter_size": "14.8B"}},
                    {"name": "llama3.1:8b", "details": {"parameter_size": "8.0B"}},
                ]
            }
        ).encode(),
    )
    r = local_detect.detect("ollama", base_url=f"{base}/v1")
    assert r.running and r.error == ""
    assert [m.model_id for m in r.models] == ["qwen2.5:14b", "llama3.1:8b"]
    assert r.models[0].parameter_size == "14.8B"


def test_ollama_skips_embedding_models(server):
    base, routes = server
    routes["/api/tags"] = (
        200,
        json.dumps(
            {
                "models": [
                    {"name": "qwen2.5:14b", "details": {"family": "qwen2"}},
                    {
                        "name": "nomic-embed-text:latest",
                        "details": {"family": "nomic-bert", "families": ["nomic-bert"]},
                    },
                    {"name": "mxbai-embed-large:latest", "details": {"family": "bert"}},
                ]
            }
        ).encode(),
    )
    r = local_detect.detect("ollama", base_url=f"{base}/v1")
    assert [m.model_id for m in r.models] == ["qwen2.5:14b"]


def test_ollama_entry_without_details_is_listed_as_basic(server):
    base, routes = server
    routes["/api/tags"] = (200, json.dumps({"models": [{"name": "tiny:latest"}]}).encode())
    r = local_detect.detect("ollama", base_url=f"{base}/v1")
    assert r.running
    assert r.models == [local_detect.LocalModel("tiny:latest", "")]
    assert local_detect.quality_label(r.models[0].parameter_size) == "Basic"


def test_lmstudio_lists_ids(server):
    base, routes = server
    routes["/v1/models"] = (
        200,
        json.dumps({"data": [{"id": "qwen2.5-14b-instruct"}, {"id": "phi-4"}]}).encode(),
    )
    r = local_detect.detect("lmstudio", base_url=f"{base}/v1")
    assert r.running
    assert [m.model_id for m in r.models] == ["qwen2.5-14b-instruct", "phi-4"]
    assert all(m.parameter_size == "" for m in r.models)


def test_connection_refused_is_not_running():
    port = _free_port()
    r = local_detect.detect("ollama", base_url=f"http://127.0.0.1:{port}/v1", timeout_s=0.5)
    assert r.running is False
    assert r.models == []
    assert r.error  # names the failure, e.g. URLError: ... refused


def test_malformed_json_is_not_running(server):
    base, routes = server
    routes["/api/tags"] = (200, b"<html>not json</html>")
    r = local_detect.detect("ollama", base_url=f"{base}/v1")
    assert r.running is False and "unexpected response" in r.error


def test_unexpected_shape_is_not_running(server):
    base, routes = server
    routes["/v1/models"] = (200, json.dumps([1, 2, 3]).encode())
    r = local_detect.detect("lmstudio", base_url=f"{base}/v1")
    assert r.running is False and "unexpected response" in r.error


def test_http_error_is_not_running(server):
    base, routes = server
    routes["/api/tags"] = (500, b"{}")
    r = local_detect.detect("ollama", base_url=f"{base}/v1")
    assert r.running is False and "HTTPError" in r.error


def test_unknown_runtime_raises():
    with pytest.raises(ValueError):
        local_detect.detect("banana")


def test_non_http_service_is_not_running():
    """A raw TCP service that doesn't speak HTTP triggers http.client.HTTPException."""
    import socket as sock_module
    import time

    def tcp_server(s):
        try:
            conn, _ = s.accept()
            # Send a malformed status line: just newlines without a valid HTTP response.
            # urllib will try to parse this and http.client will raise BadStatusLine.
            conn.send(b"\r\n")
            # Keep socket open briefly to avoid immediate close errors
            time.sleep(0.5)
            conn.close()
        except Exception:
            pass
        finally:
            s.close()

    # Listen before detect() connects; the thread only accepts on this socket.
    s = sock_module.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]

    t = threading.Thread(target=tcp_server, args=(s,), daemon=True)
    t.start()

    r = local_detect.detect("ollama", base_url=f"http://127.0.0.1:{port}/v1", timeout_s=2.0)
    assert r.running is False
    assert "unexpected response" in r.error


def test_default_base_urls():
    assert local_detect.RUNTIMES == {
        "ollama": "http://localhost:11434/v1",
        "lmstudio": "http://localhost:1234/v1",
    }
    assert local_detect.RUNTIME_NAMES == {"ollama": "Ollama", "lmstudio": "LM Studio"}


@pytest.mark.parametrize(
    "size, label",
    [
        ("", "Basic"),
        ("unknown", "Basic"),
        ("1.5B", "Basic"),
        ("7B", "Basic"),
        ("8.0B", "Basic"),
        ("11.9B", "Basic"),
        ("12B", "Good"),
        ("14.8B", "Good"),
        ("70B", "Good"),
        ("  32b ", "Good"),
    ],
)
def test_quality_label_table(size, label):
    assert local_detect.quality_label(size) == label
