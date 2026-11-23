<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api, post } from '../api.js'

const props = defineProps({ stream: Object, connected: Boolean })
const sources = ref([]), sourceId = ref(''), defaults = ref({})
const loadingSources = ref(true), submitting = ref(false), waitingFrom = ref(null), error = ref('')
const idleStates = ['completed', 'failed', 'stopped', 'interrupted']
const sessionId = computed(() => props.stream?.session_id || '')
const active = computed(() => Boolean(props.stream && !idleStates.includes(props.stream.status)))
const busy = computed(() => submitting.value || waitingFrom.value !== null || active.value)
const source = computed(() => sources.value.find(item => item.id === sourceId.value))
const position = computed(() => props.stream?.source_id === sourceId.value ? props.stream.image_position : null)
const total = computed(() => position.value?.total ?? source.value?.count ?? 0)
const canInfer = computed(() => props.connected && !busy.value && total.value > 0)

watch(sessionId, () => { waitingFrom.value = null })
watch(sourceId, () => { error.value = '' })

onMounted(async () => {
  try {
    const capabilities = await api('/capabilities')
    sources.value = capabilities.sources.filter(item => item.mode === 'finite' && !item.error && item.count > 0)
    defaults.value = capabilities.defaults
    const lastSource = sources.value.find(item => item.id === props.stream?.source_id && props.stream.image_position)
    sourceId.value = lastSource?.id ?? sources.value[0]?.id ?? ''
  } catch (exc) {
    error.value = exc.message
  } finally {
    loadingSources.value = false
  }
})

async function infer(index) {
  if (!canInfer.value || index < 1 || index > total.value) return
  submitting.value = true
  error.value = ''
  const previousSession = sessionId.value
  try {
    const { confidence, iou, image_size, max_det } = defaults.value
    await post('/runs', { source_id: sourceId.value, image_index: index, confidence, iou, image_size, max_det })
    if (sessionId.value === previousSession) waitingFrom.value = previousSession
  } catch (exc) {
    error.value = exc.message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="panel single-image-panel" aria-labelledby="single-image-heading">
    <h2 id="single-image-heading">单张推理</h2>
    <label>图片目录
      <select v-model="sourceId" :disabled="busy || loadingSources || !sources.length">
        <option v-if="!sources.length" value="">{{ loadingSources ? '正在读取目录' : '无可用图片目录' }}</option>
        <option v-for="item in sources" :key="item.id" :value="item.id">{{ item.label }}</option>
      </select>
    </label>
    <div class="single-image-actions">
      <button type="button" :disabled="!canInfer || !position || position.index <= 1" @click="infer(position.index - 1)">上一张</button>
      <button type="button" class="single-image-primary" :disabled="!canInfer" @click="infer(position?.index ?? 1)">{{ position ? '推理当前张' : '推理第一张' }}</button>
      <button type="button" :disabled="!canInfer || !position || position.index >= total" @click="infer(position.index + 1)">下一张</button>
    </div>
    <span class="single-image-position" aria-live="polite">{{ position?.index ?? '—' }} / {{ total }} 张</span>
    <p v-if="error" class="danger" role="alert">{{ error }}</p>
    <p v-else-if="busy" role="status">{{ submitting || waitingFrom !== null || (active && position) ? '正在推理' : '已有任务正在运行' }}</p>
  </section>
</template>

<style scoped>
.single-image-panel { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; padding: 12px 16px; }
h2 { font-size: 14px; margin: 0; }
label, .single-image-position { font-size: 13px; color: #a6afb8; }
label { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; min-width: 0; }
select, button { border: 1px solid #465160; border-radius: 6px; padding: 6px 9px; font: inherit; color: #e8edf0; background: #202832; }
select { max-width: 100%; }
.single-image-actions { display: flex; flex-wrap: wrap; gap: 6px; }
button { font-size: 13px; cursor: pointer; }
button:disabled { cursor: default; opacity: .45; }
.single-image-primary { border-color: #83cbaa; }
.single-image-position { white-space: nowrap; font-variant-numeric: tabular-nums; }
p { flex-basis: 100%; margin: 0; font-size: 13px; }
</style>
