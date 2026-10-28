import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { validateSnapshot, toViewInput, legacyViewInput, displayOrigin, previewUrl, frameKey } from '../src/stream/contract.js'
import { createFrameLoader } from '../src/stream/frameLoader.js'

const origin = 'http://127.0.0.1:8878'
const fixture = (id = '1') => ({ schema_version: '1.0', type: 'snapshot', revision: 1,
  stream: { session_id: 'run-a', classes: [{ id: 0, label: '测试' }] },
  frame: { frame_key: { source_id: 'camera', session_id: 'capture-a', frame_id: id }, stream_session_id: 'run-a', id, status: 'ok', coordinate_space: 'source_pixels', width: 4096, height: 2168,
    detections: [{ id: 1, class_id: 0, confidence: 0, geometry_type: 'obb', polygon_px: [[0, 0], [100, 0], [100, 40], [0, 40]], center_px: [50, 20], angle_deg: 0, orientation_valid: true }],
    preview: { id, url: `/preview/${id}.jpg`, width: 1024, height: 542, sx: .25, sy: .25, ox: 0, oy: 0 }, preview_status: 'ready' } })
const tick = () => new Promise(resolve => setTimeout(resolve, 0))

test('same contract accepts different model classes and retains valid zeros', () => {
  const first = fixture()
  assert.equal(validateSnapshot(first).frame.detections[0].confidence, 0)
  const other = fixture('99')
  other.stream.classes = [{ id: 'steel', label: '钢片' }]
  other.frame.detections[0].class_id = 'steel'
  assert.equal(toViewInput(validateSnapshot(other)).detections[0].angle_deg, 0)
  assert.notEqual(frameKey(first.frame), frameKey(other.frame))
})
test('rejects incompatible version, mismatched session, malformed points and invalid angle', () => {
  for (const change of [v => v.schema_version = '2.0', v => v.frame.coordinate_space = 'normalized', v => v.frame.stream_session_id = 'old-run', v => v.frame.detections[0].polygon_px[0][0] = NaN, v => v.frame.detections[0].angle_deg = 180]) {
    const input = fixture(); change(input); assert.throws(() => validateSnapshot(input), /展示协议错误/)
  }
})
test('empty successful detection is different from error', () => {
  const empty = fixture(); empty.frame.detections = []
  assert.equal(validateSnapshot(empty).frame.status, 'ok')
  const error = fixture(); error.frame.status = 'error'; error.frame.detections = []; error.frame.width = 0; error.frame.height = 0; error.frame.preview = null
  assert.equal(validateSnapshot(error).frame.status, 'error')
})
test('endpoint configuration is local-only and image URLs stay on selected service', () => {
  assert.equal(displayOrigin({ origin, search: '?display_origin=http://localhost:8879' }), 'http://localhost:8879')
  for (const query of ['https://example.com', 'http://127.0.0.1:8879/path', 'http://user:secret@localhost:8879']) assert.throws(() => displayOrigin({ origin, search: '?display_origin=' + encodeURIComponent(query) }))
  assert.equal(previewUrl('/image.jpg', origin), origin + '/image.jpg')
  assert.throws(() => previewUrl('http://elsewhere.test/image.jpg', origin))
})
test('legacy history conversion does not invent a valid angle', () => {
  const input = legacyViewInput({ id: 7, run_id: 'saved', status: 'ok', width: 200, height: 100, image_url: '/image', detections: [{ id: 1, polygon: [[10, 10], [30, 10], [30, 20], [10, 20]] }] })
  assert.equal(input.preview.sx, 1)
  assert.deepEqual(input.detections[0].center, [20, 15])
  assert.equal(input.detections[0].orientation_valid, false)
})
test('late previous image cannot overwrite newer frame; all object URLs released', async () => {
  const wait = new Map(), states = [], released = []
  const loader = createFrameLoader({ origin, onState: s => states.push(s),
    fetchImage: async url => ({ ok: true, blob: async () => url }), createUrl: blob => blob,
    revokeUrl: url => released.push(url), decode: url => new Promise(resolve => wait.set(url, resolve)) })
  const one = loader.load(toViewInput(fixture('1'))); await tick()
  const two = loader.load(toViewInput(fixture('2'))); await tick()
  wait.get(origin + '/preview/2.jpg')({ width: 1024, height: 542 }); await two
  assert.equal(states.at(-1).frame.id, '2')
  wait.get(origin + '/preview/1.jpg')({ width: 1024, height: 542 }); await one
  assert.equal(states.at(-1).frame.id, '2')
  assert.deepEqual(states.at(-1).frame.imageRect, { x: -0, y: -0, width: 4096, height: 2168 })
  loader.dispose()
  assert.equal(released.length, 2)
})
test('preview metadata mismatch clears frame instead of rendering wrong coordinates', async () => {
  const states = [], released = []
  const loader = createFrameLoader({ origin, onState: s => states.push(s), fetchImage: async () => ({ ok: true, blob: async () => 'blob' }), createUrl: x => x, revokeUrl: x => released.push(x), decode: async () => ({ width: 1, height: 1 }) })
  await loader.load(toViewInput(fixture()))
  assert.equal(states.at(-1).frame, null)
  assert.match(states.at(-1).error, /尺寸/)
  loader.dispose(); assert.deepEqual(released, ['blob'])
})
test('disconnect retains complete frame while invalidating an unfinished decode', async () => {
  let finish; const states = []
  const loader = createFrameLoader({ origin, onState: s => states.push(s), fetchImage: async () => ({ ok: true, blob: async () => 'blob' }), createUrl: x => x, revokeUrl: () => {}, decode: async () => ({ width: 1024, height: 542 }) })
  await loader.load(toViewInput(fixture()))
  loader.disconnect(); assert.equal(states.at(-1).frame.id, '1'); loader.dispose()
  const pending = createFrameLoader({ origin, onState: s => states.push(s), fetchImage: async () => ({ ok: true, blob: async () => 'blob' }), createUrl: x => x, revokeUrl: () => {}, decode: () => new Promise(resolve => finish = resolve) })
  const work = pending.load(toViewInput(fixture('2'))); await tick(); pending.disconnect(); finish({ width: 1024, height: 542 }); await work
  assert.equal(states.at(-1).frame, null); pending.dispose()
})
test('canvas has no transport or legacy run coupling', async () => {
  const canvas = await readFile(new URL('../src/components/DetectionStage.vue', import.meta.url), 'utf8')
  assert.doesNotMatch(canvas, /fetch\(|WebSocket|image_url|run_id|from ['"].*api/)
})

test('continuous fast input does not starve slow decoding and queue retains only newest', async () => {
  const waiting = new Map(), started = [], states = []
  const loader = createFrameLoader({ origin, strategy: 'latest', onState: s => states.push(s), fetchImage: async url => { started.push(url); return { ok: true, blob: async () => url } }, createUrl: x => x, revokeUrl: () => {}, decode: url => new Promise(resolve => waiting.set(url, resolve)) })
  const first = loader.load(toViewInput(fixture('1'))); await tick()
  for (let n = 2; n <= 40; n++) await loader.load(toViewInput(fixture(String(n))))
  assert.equal(started.length, 1)
  waiting.get(origin + '/preview/1.jpg')({ width: 1024, height: 542 }); await first; await tick()
  assert.equal(states.some(s => s.frame?.id === '1'), true)
  assert.equal(states.at(-1).frame.id, '1')
  assert.equal(started.length, 2)
  assert.match(started[1], /40\.jpg$/)
  waiting.get(origin + '/preview/40.jpg')({ width: 1024, height: 542 }); await tick()
  assert.equal(states.at(-1).frame.id, '40')
  loader.dispose()
})

test('stream session switch cancels old decode even with latest-queue strategy', async () => {
  const waiting = new Map(), states = []
  const loader = createFrameLoader({ origin, strategy: 'latest', onState: s => states.push(s), fetchImage: async url => ({ ok: true, blob: async () => url }), createUrl: x => x, revokeUrl: () => {}, decode: url => new Promise(resolve => waiting.set(url, resolve)) })
  const first = loader.load(toViewInput(fixture('1'))); await tick()
  const next = fixture('2'); next.stream.session_id = next.frame.stream_session_id = 'run-b'
  const second = loader.load(toViewInput(next)); await tick()
  waiting.get(origin + '/preview/2.jpg')({ width: 1024, height: 542 }); await second
  waiting.get(origin + '/preview/1.jpg')({ width: 1024, height: 542 }); await first
  assert.equal(states.at(-1).frame.sessionId, 'run-b')
  assert.equal(states.at(-1).frame.id, '2'); loader.dispose()
})
