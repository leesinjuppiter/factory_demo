"""隔离schema上的新版展示/持续文件来源集成，不停共享服务。"""
import importlib.util
import json
import time
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest
from starlette.websockets import WebSocketDisconnect

from test_api import context, start, finish

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('camera_publish', ROOT/'scripts/simulate_camera.py')
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)


def until(fn):
    limit = time.monotonic() + 8
    while time.monotonic() < limit:
        value = fn()
        if value: return value
        time.sleep(.02)
    raise AssertionError('condition timed out')


def test_display_snapshot_and_preview_do_not_read_database(context):
    client, cfg, _ = context
    # A valid upload ensures the final frame has a preview rather than the bad-file fixture.
    image = cv2.imencode('.png', np.full((60, 100, 3), 80, np.uint8))[1].tobytes()
    source = client.post('/api/uploads', files={'file':('valid.png', image, 'image/png')}).json()['source_id']
    run_id = start(client, source_id=source)
    finish(client, run_id)
    packet = until(lambda: (p if (p := client.get('/api/display/snapshot').json())['frame'] and p['frame']['preview'] else None))
    assert packet['schema_version'] == '1.0'
    assert packet['frame']['detections'][0]['center_px'] == [8.5, 8.5]
    assert 'path' not in json.dumps(packet).lower()
    with patch.object(client.app.state.store, 'frame', side_effect=AssertionError('must not read DB')):
        assert client.get('/api/status').status_code == 200
        assert client.get('/api/display/snapshot').status_code == 200
        response = client.get(packet['frame']['preview']['url'])
        assert response.status_code == 200
        assert cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR).shape == (60,100,3)
        with client.websocket_connect('/api/display/ws') as ws:
            current = ws.receive_json()
            assert current['frame']['frame_key'] == packet['frame']['frame_key']
            ws.send_json({'type':'pause'})
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
            assert closed.value.code == 1008
    assert client.get('/api/display/previews/missing.jpg').status_code == 410


def test_continuous_inbox_idle_publish_stop_restart_receipts(context):
    client, cfg, _ = context
    inbox = cfg.runtime / 'inbox'
    inbox.mkdir()
    cfg.sources['inbox'] = {'id':'inbox','label':'test camera','path':inbox,'mode':'inbox'}
    run_id = start(client, source_id='inbox')
    until(lambda: client.get('/api/status').json()['run']['status'] == 'running')
    assert client.get('/api/status').json()['run']['total'] is None
    data = cv2.imencode('.png', np.full((60,100,3), 80, np.uint8))[1].tobytes()
    for seq in range(1,4): sim.publish(inbox,data,'.png','camera_test','camera_session',seq)
    until(lambda: client.get('/api/status').json()['run']['processed'] == 3)
    assert client.get('/api/status').json()['run']['status'] == 'running'
    packet = until(lambda: (p if (p := client.get('/api/display/snapshot').json())['frame'] and p['frame']['preview'] else None))
    assert packet['frame']['frame_key']['session_id'] == 'camera_session'
    assert packet['frame']['capture_time'] is None
    assert client.post(f'/api/runs/{run_id}/control', json={'action':'pause'}).status_code == 200
    until(lambda: client.get('/api/status').json()['run']['status'] == 'paused')
    assert client.post(f'/api/runs/{run_id}/control', json={'action':'stop'}).status_code == 200
    assert finish(client,run_id)['status'] == 'stopped'
    next_id = start(client,source_id='inbox')
    until(lambda: client.get('/api/status').json()['run']['status'] == 'running')
    time.sleep(.25)
    assert client.get('/api/status').json()['run']['processed'] == 0
    sim.publish(inbox,data,'.png','camera_test','new_session',1)
    until(lambda: client.get('/api/status').json()['run']['processed'] == 1)
    client.post(f'/api/runs/{next_id}/control',json={'action':'stop'})
    assert finish(client,next_id)['status'] == 'stopped'
    assert len(list(inbox.glob('*.png'))) == 4
