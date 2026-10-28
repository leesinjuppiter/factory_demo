"""Mapped port serves only display data; no database or model dependency."""
import asyncio
import json
from pathlib import Path
import sys
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import display_gateway as gateway


@pytest.fixture
def context(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<html><head></head><body>display</body></html>')
    for name in ("display-a.js", "style-b.css", "admin-c.js"):
        (dist / "assets" / name).write_text(name)
    (dist / "admin.html").write_text('private admin')
    monkeypatch.setattr(gateway, "DIST", dist)
    seen = []

    def respond(request):
        seen.append(str(request.url))
        if request.url.path.endswith('.jpg'):
            return httpx.Response(200, content=b'jpeg', headers={'content-type': 'image/jpeg'})
        return httpx.Response(200, json={'schema_version': '1.0', 'type': 'snapshot'})

    app = gateway.create_display_app('display.example.com', transport=httpx.MockTransport(respond))
    with TestClient(app) as client:
        yield client, seen


def test_public_html_and_display_assets(context):
    client, _ = context
    response = client.get('/', headers={'Host': 'display.example.com:8443'})
    assert response.status_code == 200
    assert 'factory-display-readonly' in response.text
    assert client.get('/assets/display-a.js').status_code == 200
    assert client.get('/assets/style-b.css').status_code == 200
    assert client.get('/', headers={'Host': 'untrusted.example'}).status_code == 400


@pytest.mark.parametrize('path', ['/admin.html', '/api/status', '/api/runs', '/api/capabilities', '/api/health', '/api/uploads', '/docs', '/openapi.json', '/.env', '/assets/admin-c.js', '/assets/..%2Fadmin.html'])
def test_private_routes_and_admin_assets_not_exposed(context, path):
    client, seen = context
    assert client.get(path).status_code == 404
    assert not seen


def test_display_proxy_uses_fixed_upstream_and_preserves_image_type(context):
    client, seen = context
    assert client.get('/api/display/snapshot?url=http://untrusted.example').status_code == 200
    assert seen == ['http://127.0.0.1:8765/api/display/snapshot']
    response = client.get('/api/display/previews/'+'a'*32+'.jpg')
    assert response.status_code == 200 and response.headers['content-type'] == 'image/jpeg'
    assert client.get('/api/display/previews/not-a-cache-id.jpg').status_code == 422
    assert client.post('/api/display/snapshot', json={}).status_code == 405
    assert client.post('/api/runs', json={}).status_code == 404


def test_upstream_failure_is_bounded_and_generic(monkeypatch):
    def unavailable(request):
        raise httpx.ConnectError('private internal address', request=request)
    app = gateway.create_display_app(transport=httpx.MockTransport(unavailable))
    with TestClient(app) as client:
        response = client.get('/api/display/snapshot')
        assert response.status_code == 503
        assert 'private internal address' not in response.text


def test_websocket_relays_snapshot_and_rejects_client_messages(context):
    client, _ = context
    class Upstream:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def __aiter__(self):
            yield json.dumps({'type': 'snapshot', 'schema_version': '1.0'})
            await asyncio.Event().wait()
    with patch.object(gateway, 'connect', return_value=Upstream()) as upstream:
        with client.websocket_connect('/api/display/ws', headers={'Origin': 'https://display.example.com:8443'}) as ws:
            assert ws.receive_json()['type'] == 'snapshot'
            assert upstream.call_args.kwargs['origin'] == 'http://127.0.0.1:8765'
            ws.send_json({'action': 'stop'})
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
            assert closed.value.code == 1008
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect('/api/display/ws', headers={'Origin': 'https://untrusted.example'}): pass
    assert closed.value.code == 1008
