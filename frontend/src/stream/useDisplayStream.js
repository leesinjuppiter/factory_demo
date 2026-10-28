import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { displayOrigin, toViewInput, validateSnapshot } from './contract.js'
import { usePreparedFrame } from './usePreparedFrame'

export function useDisplayStream() {
  const snapshot = ref(null), connected = ref(false), checked = ref(false), error = ref(''), lastContact = ref(null)
  let origin = window.location.origin
  try { origin = displayOrigin(window.location) } catch (e) { error.value = e.message }
  const validOrigin = !error.value
  const input = computed(() => snapshot.value ? toViewInput(snapshot.value) : null)
  const prepared = usePreparedFrame(input, connected, origin, 'latest')
  let socket, retryTimer, heartbeatTimer, disposed = false, generation = 0, revision = -1
  const maxSilenceMs = 45000
  function touch() { lastContact.value = new Date(); clearTimeout(heartbeatTimer); heartbeatTimer = setTimeout(() => socket?.close(), maxSilenceMs) }
  function connect() {
    if (disposed || !validOrigin) { checked.value = true; return }
    const token = ++generation
    revision = -1
    const url = new URL('/api/display/ws', origin); url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    socket = new WebSocket(url)
    socket.onopen = () => { if (token !== generation) return; checked.value = true; touch() }
    socket.onmessage = event => {
      if (disposed || token !== generation) return
      try {
        const value = JSON.parse(event.data)
        if (value.type === 'heartbeat') { if (!/^1\.\d+$/.test(value.schema_version || '')) throw new Error('不支持的展示协议版本'); touch(); return }
        const next = validateSnapshot(value)
        if (next.revision <= revision) return
        revision = next.revision
        snapshot.value = next
        connected.value = true; checked.value = true; error.value = ''; touch()
      } catch (e) { error.value = e.message; connected.value = false; socket.close() }
    }
    socket.onerror = () => { if (token === generation) { connected.value = false; checked.value = true } }
    socket.onclose = () => {
      if (disposed || token !== generation) return
      connected.value = false; checked.value = true; clearTimeout(heartbeatTimer)
      retryTimer = setTimeout(connect, 2000)
    }
  }
  onMounted(connect)
  onBeforeUnmount(() => { disposed = true; generation++; clearTimeout(retryTimer); clearTimeout(heartbeatTimer); socket?.close() })
  return { snapshot, prepared, connected, checked, error, lastContact, origin }
}
