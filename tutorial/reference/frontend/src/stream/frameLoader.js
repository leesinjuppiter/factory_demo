import { previewUrl } from './contract.js'

export function decodeImage(url, signal) {
  return new Promise((resolve, reject) => {
    const image = new Image()
    const abort = () => { image.src = ''; reject(new Error('图片加载已取消')) }
    const finish = fn => { signal.removeEventListener('abort', abort); image.onload = image.onerror = null; fn() }
    image.onload = () => finish(() => resolve({ width: image.naturalWidth, height: image.naturalHeight }))
    image.onerror = () => finish(() => reject(new Error('图片解码失败')))
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) abort()
    else image.src = url
  })
}

// 单个浏览器最多一个取图请求；图片和检测数据在解码后一起提交。
export function createFrameLoader({ onState, origin, strategy = 'replace', fetchImage = fetch, decode = decodeImage, createUrl = URL.createObjectURL, revokeUrl = URL.revokeObjectURL, timeoutMs = 10000 }) {
  let generation = 0, controller = null, shownUrl = '', shown = null, pendingKey = '', pendingSession = null, queued = null, disposed = false
  function clear() { if (shownUrl) revokeUrl(shownUrl); shownUrl = ''; shown = null }
  function cancelPending() { generation++; controller?.abort(); controller = null; pendingKey = ''; pendingSession = null; queued = null }
  async function load(input) {
    if (disposed) return
    const key = input?.preview ? `${input.key}/${input.preview.id}` : ''
    if (key && key === pendingKey) return
    if (key && key === shown?.loadKey) return
    const sameSession = input && input.sessionId === (pendingSession ?? shown?.sessionId)
    if (strategy === 'latest' && sameSession && input.status === 'ok') {
      if (controller && input.preview) {
        // Do not cancel work at every new frame: that starves a slow decoder.
        // One in-flight image plus the newest waiting input bounds memory.
        queued = input
        onState({ frame: shown, loading: true, error: '' })
        return
      }
      if (!input.preview) {
        onState({ frame: shown, loading: input.previewStatus === 'pending', error: input.previewStatus === 'error' ? '新帧预览生成失败，保留最后完整画面。' : '' })
        return
      }
    }
    cancelPending()
    const keepShown = strategy === 'latest' && sameSession
    if (!input || input.status !== 'ok' || !input.preview) {
      if (!keepShown) clear()
      onState({ frame: shown, loading: input?.status === 'ok' && input.previewStatus === 'pending', error: input?.error || (input?.previewStatus === 'error' ? '预览生成失败；检测结果不等于空检测。' : '') })
      return
    }
    if (!keepShown) clear()
    pendingKey = key
    pendingSession = input.sessionId
    const token = generation, abort = new AbortController()
    controller = abort
    onState({ frame: shown, loading: true, error: '' })
    const timer = setTimeout(() => abort.abort(), timeoutMs)
    let objectUrl = ''
    try {
      const response = await fetchImage(previewUrl(input.preview.url, origin), { signal: abort.signal })
      if (!response.ok) throw new Error(response.status === 404 || response.status === 410 ? '预览已过期或不存在，等待新画面。' : `预览读取失败（HTTP ${response.status}）`)
      objectUrl = createUrl(await response.blob())
      const size = await decode(objectUrl, abort.signal)
      if (size.width !== input.preview.width || size.height !== input.preview.height) throw new Error('预览实际尺寸与协议不一致')
      if (disposed || token !== generation) return
      const p = input.preview
      if (shownUrl) revokeUrl(shownUrl)
      shownUrl = objectUrl; objectUrl = ''
      shown = { ...input, loadKey: key, displayUrl: shownUrl, imageRect: { x: -p.ox / p.sx, y: -p.oy / p.sy, width: p.width / p.sx, height: p.height / p.sy } }
      onState({ frame: shown, loading: false, error: '' })
    } catch (error) {
      if (!disposed && token === generation) onState({ frame: shown, loading: false, error: abort.signal.aborted ? '预览读取超时，等待新画面或重新连接。' : error.message })
    } finally {
      clearTimeout(timer)
      if (objectUrl) revokeUrl(objectUrl)
      if (token === generation) {
        controller = null; pendingKey = ''; pendingSession = null
        const next = queued; queued = null
        if (next) void load(next)
      }
    }
  }
  return { load, disconnect() { cancelPending(); onState({ frame: shown, loading: false, error: '' }) }, dispose() { disposed = true; cancelPending(); clear() } }
}
