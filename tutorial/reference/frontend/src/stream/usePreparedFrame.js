import { onBeforeUnmount, ref, watch } from 'vue'
import { createFrameLoader } from './frameLoader.js'

export function usePreparedFrame(input, connected, origin = window.location.origin, strategy = 'replace') {
  const prepared = ref({ frame: null, loading: false, error: '' })
  const loader = createFrameLoader({ origin, strategy, onState: value => { prepared.value = value } })
  watch([input, connected], ([value, online], previous = []) => {
    if (!online && previous[1]) loader.disconnect()
    else loader.load(value)
  }, { immediate: true })
  onBeforeUnmount(() => loader.dispose())
  return prepared
}
