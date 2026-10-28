// 展示协议只包含可显示数据；不认识数据库表或推理引擎。
const finite = Number.isFinite
const point = p => Array.isArray(p) && p.length === 2 && p.every(finite)
const identifier = v => (typeof v === 'string' && v.length > 0 && v.length <= 200) || (Number.isSafeInteger(v) && v >= 0)
const problem = text => { throw new Error(`展示协议错误：${text}`) }
export const errorText = value => typeof value === 'string' ? value : value?.message || ''

export function frameKey(frame) {
  const key = frame?.frame_key
  return key ? JSON.stringify([key.source_id, key.session_id, key.frame_id]) : ''
}

export function validateSnapshot(value) {
  if (!value || value.type !== 'snapshot' || !/^1\.\d+$/.test(value.schema_version || '')) problem('不支持的协议版本或消息类型')
  if (!Number.isSafeInteger(value.revision) || value.revision < 0) problem('revision 无效')
  if (value.stream === null) {
    if (value.frame !== null) problem('没有数据流却包含帧')
    return value
  }
  const stream = value.stream
  if (!stream || !identifier(stream.session_id) || !Array.isArray(stream.classes)) problem('缺少会话或类别目录')
  const ids = new Set()
  for (const category of stream.classes) {
    if (!identifier(category.id) || ids.has(String(category.id))) problem('类别标识无效或重复')
    ids.add(String(category.id))
  }
  const frame = value.frame
  if (frame === null) return value
  if (!frame || !frame.frame_key || !['source_id', 'session_id', 'frame_id'].every(k => typeof frame.frame_key[k] === 'string' && frame.frame_key[k].length > 0)) problem('帧身份无效')
  if (frame.stream_session_id !== stream.session_id) problem('帧与数据流会话不一致')
  if (frame.coordinate_space !== 'source_pixels') problem('坐标必须使用原图像素空间')
  if (!['ok', 'error'].includes(frame.status) || !Array.isArray(frame.detections)) problem('帧状态无效')
  if (frame.status === 'ok' && (![frame.width, frame.height].every(v => Number.isSafeInteger(v) && v > 0) || frame.width * frame.height > 100_000_000)) problem('图像尺寸无效')
  if (frame.detections.length > 10000) problem('目标数量超过展示上限')
  const detections = new Set()
  for (const d of frame.detections) {
    if (!identifier(d.id) || detections.has(String(d.id)) || !ids.has(String(d.class_id))) problem('检测编号或类别无效')
    detections.add(String(d.id))
    if (!['hbb', 'obb'].includes(d.geometry_type)) problem('仅支持 HBB/OBB 二维检测')
    if (!finite(d.confidence) || d.confidence < 0 || d.confidence > 1 || !Array.isArray(d.polygon_px) || d.polygon_px.length !== 4 || !d.polygon_px.every(point) || !point(d.center_px)) problem('检测几何或置信度无效')
    if (typeof d.orientation_valid !== 'boolean' || (d.orientation_valid && (!finite(d.angle_deg) || d.angle_deg < 0 || d.angle_deg >= 180))) problem('角度无效')
  }
  const p = frame.preview
  if (p != null && (!identifier(p.id) || typeof p.url !== 'string' || ![p.width, p.height].every(v => Number.isSafeInteger(v) && v > 0) || ![p.sx, p.sy].every(v => finite(v) && v > 0) || ![p.ox, p.oy].every(finite))) problem('预览尺寸或坐标变换无效')
  return value
}

// 只允许本机端点；同一份构建可用 ?display_origin=http://127.0.0.1:8878 切换模拟服务。
export function displayOrigin(location) {
  const selected = new URLSearchParams(location.search).get('display_origin')
  const url = new URL(selected || location.origin)
  if (!['http:', 'https:'].includes(url.protocol) || !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) || url.username || url.password || url.pathname !== '/' || url.search || url.hash) throw new Error('展示地址必须是本机 HTTP/HTTPS 服务的 origin')
  return url.origin
}

export function previewUrl(raw, origin) {
  const url = new URL(raw, origin)
  if (!['http:', 'https:'].includes(url.protocol) || url.origin !== origin || url.username || url.password) throw new Error('预览地址必须属于选定的展示服务')
  return url.href
}

export function toViewInput(snapshot) {
  const frame = snapshot.frame
  if (!frame) return null
  return {
    key: frameKey(frame), sessionId: frame.stream_session_id, id: frame.id || frame.frame_key.frame_id,
    name: frame.name, status: frame.status, width: frame.width, height: frame.height,
    created_at: frame.created_at, capture_time: frame.capture_time, timing_ms: frame.timing_ms,
    error: errorText(frame.error), preview: frame.preview, previewStatus: frame.preview_status,
    classes: snapshot.stream.classes.map(c => ({ ...c })),
    detections: frame.detections.map(d => ({ ...d, polygon: d.polygon_px.map(p => [...p]), center: [...d.center_px] })),
  }
}

// 旧历史 API 仅在此处适配，不进入画布或通用实时协议。
export function legacyViewInput(frame, classes = []) {
  if (!frame) return null
  return {
    key: JSON.stringify(['history', frame.run_id, String(frame.id)]), sessionId: frame.run_id, id: String(frame.id),
    name: frame.name, status: frame.status, width: frame.width, height: frame.height,
    created_at: frame.created_at, timing_ms: frame.timing_ms, error: errorText(frame.error),
    classes: classes.map(c => ({ ...c })),
    preview: frame.status === 'ok' && frame.image_url ? { id: `${frame.run_id}/${frame.id}`, url: frame.image_url, width: frame.width, height: frame.height, sx: 1, sy: 1, ox: 0, oy: 0 } : null,
    detections: (frame.detections || []).map(d => ({ ...d, polygon: d.polygon.map(p => [...p]), center: d.center_px || [d.polygon.reduce((s, p) => s + p[0], 0) / 4, d.polygon.reduce((s, p) => s + p[1], 0) / 4], angle_deg: d.angle_deg ?? null, orientation_valid: d.orientation_valid === true })),
  }
}
