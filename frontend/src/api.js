// 每个请求都有限时；业务错误和断线统一转为可读消息。
export async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, { ...options, signal: AbortSignal.timeout(10000) })
  const contentType = response.headers.get('content-type') || ''
  const data = contentType.includes('json') ? await response.json() : null
  if (!response.ok) {
    const detail = data?.detail
    throw new Error(detail?.message || (typeof detail === 'string' ? detail : `请求失败（HTTP ${response.status}）`))
  }
  if (!data) throw new Error('服务返回了非 JSON 响应，请检查 API 地址。')
  return data
}

export const post = (path, body) => api(path, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
})

export async function download(url, fallbackName) {
  const response = await fetch(url, { signal: AbortSignal.timeout(60000) })
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(data?.detail?.message || `导出失败（HTTP ${response.status}）`)
  }
  const blobUrl = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = blobUrl
  link.download = fallbackName
  link.click()
  setTimeout(() => URL.revokeObjectURL(blobUrl), 1000)
}
