<script setup>
import { computed, ref, watch } from 'vue'

// 画布只消费已配对、解码的 ViewFrame；网络和旧历史协议都在 stream 层。
const props = defineProps({ frame: Object, loading: Boolean, error: String, connected: Boolean, historical: Boolean, state: String, classFilter: String, allowDownload: { type: Boolean, default: false } })
const emit = defineEmits(['download', 'display-change'])
const root = ref(null)
const loaded = computed(() => props.frame)
const displayUrl = computed(() => props.frame?.displayUrl || '')
const localError = ref('')
const imageError = computed(() => props.error || localError.value)
const loading = computed(() => props.loading)
const showBoxes = ref(true), showLabels = ref(true), showCoordinates = ref(false)
const zoom = ref(1), cursor = ref(null), selectedId = ref(null)
const detections = computed(() => (loaded.value?.detections || []).filter(d => !props.classFilter || String(d.class_id) === props.classFilter))
const selected = computed(() => detections.value.find(d => d.id === selectedId.value))
watch(() => props.frame?.key, () => { cursor.value = null; selectedId.value = null; localError.value = '' })
watch(detections, items => { if (!items.some(d => d.id === selectedId.value)) selectedId.value = null })
watch([loaded, selected, imageError, loading], () => emit('display-change', { frame: loaded.value, selected: selected.value || null, error: imageError.value, loading: loading.value }), { immediate: true })
function pointer(event) {
  const matrix = event.currentTarget.getScreenCTM()
  if (!matrix || !loaded.value) { cursor.value = null; return }
  const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
  cursor.value = p.x >= 0 && p.y >= 0 && p.x < loaded.value.width && p.y < loaded.value.height ? { x: p.x, y: p.y } : null
}
const classInfo = d => loaded.value?.classes.find(c => String(c.id) === String(d.class_id))
const color = d => classInfo(d)?.color || '#36c8b0'
const label = d => classInfo(d)?.label || d.class_name
const fontSize = computed(() => Math.max(12, (loaded.value?.width || 640) / 70))
const labelX = d => Math.max(4, Math.min(loaded.value.width - 180, d.polygon[0][0]))
const labelY = d => Math.max(fontSize.value + 4, Math.min(loaded.value.height - 4, d.polygon[0][1] - 6))
async function fullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen()
    else await root.value.requestFullscreen()
  } catch { localError.value = '浏览器未允许全屏，请使用窗口最大化。' }
}
</script>

<template>
  <section class="viewer panel" ref="root" aria-label="检测画面">
    <div class="viewer-heading">
      <div><span class="section-kicker">DETECTION VIEW</span><h2>检测画面</h2></div>
      <span class="frame-code">{{ frame ? `FRAME ${String(frame.id).padStart(4, '0')}` : '等待任务' }}</span>
    </div>
    <div class="image-stage">
      <div v-if="loaded" class="image-scroll">
        <svg :key="loaded.key" :viewBox="`0 0 ${loaded.width} ${loaded.height}`" :style="{ width: `${zoom * 100}%`, height: `${zoom * 100}%` }" preserveAspectRatio="xMidYMid meet" @pointermove="pointer" @pointerleave="cursor = null" role="img" :aria-label="`${loaded.name} 检测结果`">
          <image preserveAspectRatio="none" :href="displayUrl" :x="loaded.imageRect.x" :y="loaded.imageRect.y" :width="loaded.imageRect.width" :height="loaded.imageRect.height" />
          <g v-if="showBoxes">
            <g v-for="d in detections" :key="d.id">
              <polygon tabindex="0" role="button" :class="{ selected: selectedId === d.id }" :aria-pressed="selectedId === d.id" :aria-label="`查看目标 ${d.id} 坐标`" @click="selectedId = d.id" @keydown.enter.prevent="selectedId = d.id" @keydown.space.prevent="selectedId = d.id" style="pointer-events:all;cursor:crosshair" :points="d.polygon.map(p => p.join(',')).join(' ')" :fill="selectedId === d.id ? color(d) : 'none'" :fill-opacity="selectedId === d.id ? .12 : 0" :stroke="color(d)" :stroke-width="selectedId === d.id ? 4 : 2" vector-effect="non-scaling-stroke" />
              <text v-if="showLabels" :x="labelX(d)" :y="labelY(d)" :font-size="fontSize" :fill="color(d)" stroke="#102025" :stroke-width="fontSize / 5" paint-order="stroke" font-weight="700">#{{ d.id }} {{ label(d) }} {{ (d.confidence * 100).toFixed(1) }}%</text>
              <text v-if="showCoordinates" :x="d.polygon[0][0]" :y="d.polygon[0][1] + fontSize * 1.3" :font-size="fontSize" :fill="color(d)" stroke="#102025" :stroke-width="fontSize / 5" paint-order="stroke">{{ d.id }} · ({{ d.polygon[0][0].toFixed(1) }}, {{ d.polygon[0][1].toFixed(1) }})</text>
            </g>
          </g>
        </svg>
      </div>
      <div v-else class="empty-stage">
        <div class="viewfinder" aria-hidden="true"></div>
        <strong>{{ imageError ? '画面不可用' : loading ? '正在加载预览' : state === 'loading' ? '正在加载模型' : '准备开始检测' }}</strong>
        <p>{{ imageError || (state === 'loading' ? '首次加载可能需要一些时间，完成后自动显示结果。' : '等待后台管理创建任务，检测结果将在这里显示。') }}</p>
      </div>
      <span v-if="!historical && !connected && frame" class="stale-label">连接中断 · 当前为最后一次结果</span>
      <div v-if="loaded && !detections.length" class="no-detection">{{ loaded.detections.length ? '当前筛选下无目标' : '本图未检出目标' }}</div>
    </div>
    <div class="viewer-toolbar">
      <label><input type="checkbox" v-model="showBoxes">检测框</label>
      <label><input type="checkbox" v-model="showLabels" :disabled="!showBoxes">类别 / 置信度</label>
      <label><input type="checkbox" v-model="showCoordinates" :disabled="!showBoxes">坐标标签</label>
      <span class="toolbar-spacer"></span>
      <button class="text-button" @click="zoom = Math.max(1, zoom - .25)" :disabled="!loaded || zoom <= 1" aria-label="缩小">−</button>
      <span class="zoom-value">{{ Math.round(zoom * 100) }}%</span>
      <button class="text-button" @click="zoom = Math.min(3, zoom + .25)" :disabled="!loaded || zoom >= 3" aria-label="放大">＋</button>
      <button class="text-button" @click="zoom = 1">适应</button>
      <button class="text-button" @click="fullscreen">全屏</button>
      <button v-if="allowDownload" class="text-button" @click="emit('download')" :disabled="!loaded">导出绘框图</button>
    </div>
    <div class="coordinate-readout" aria-live="polite"><span>原图指针：{{ cursor ? `x=${cursor.x.toFixed(1)}, y=${cursor.y.toFixed(1)} px` : '—' }}</span><span v-if="selected">目标 {{ selected.id }}：{{ selected.polygon.map((p, i) => `P${i+1}(${p[0].toFixed(1)}, ${p[1].toFixed(1)})`).join(' · ') }}</span><span v-else>点击检测框或聚焦后回车查看坐标</span><span v-if="selected">中心 {{ selected.center.map(v => v.toFixed(1)).join(', ') }} px · 角度 {{ selected.orientation_valid ? selected.angle_deg.toFixed(1) + '°' : '无有效方向' }}</span></div>
    <div class="image-caption"><span :title="frame?.name">{{ frame?.name || '尚未选择图片' }}</span><span>{{ frame?.width ? `${frame.width} × ${frame.height} px` : '原图坐标 · 预览变换显示' }}</span></div>
  </section>
</template>

