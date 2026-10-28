<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import DetectionStage from './components/DetectionStage.vue'
import { useDisplayStream } from './stream/useDisplayStream.js'
import { errorText } from './stream/contract.js'
import './display.css'

const { snapshot, prepared, connected, checked, error, lastContact } = useDisplayStream()
const stream = computed(() => snapshot.value?.stream)
const frame = computed(() => prepared.value.frame)
const filter = ref(''), clock = ref(new Date()), display = ref({ frame: null, selected: null })
let clockTimer
const states = { loading: '加载模型', running: '正在运行', pausing: '正在暂停', paused: '已暂停', stopping: '正在停止', completed: '已完成', stopped: '已停止', failed: '任务失败', interrupted: '服务中断' }
const stateLabel = computed(() => states[stream.value?.status] || '等待任务')
const stateTone = computed(() => ['failed', 'interrupted'].includes(stream.value?.status) ? 'danger' : ['loading', 'pausing', 'paused', 'stopping', 'stopped'].includes(stream.value?.status) ? 'warning' : stream.value ? 'good' : 'neutral')
const classes = computed(() => frame.value?.classes || stream.value?.classes || [])
const visibleFrame = computed(() => frame.value?.sessionId === stream.value?.session_id ? frame.value : null)
const selected = computed(() => display.value.frame?.key === visibleFrame.value?.key ? display.value.selected : null)
const detections = computed(() => (visibleFrame.value?.detections || []).filter(d => filter.value === '' || String(d.class_id) === filter.value))
const progress = computed(() => stream.value?.total ? Math.min(100, stream.value.processed / stream.value.total * 100) : 0)
const engine = computed(() => stream.value?.engine_label || '—')
const timeText = computed(() => clock.value.toLocaleTimeString('zh-CN', { hour12: false }))
const dateText = computed(() => clock.value.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'short' }))
const ms = value => Number.isFinite(value) ? value.toFixed(1) : '—'
const timeOf = value => value ? new Date(value).toLocaleTimeString('zh-CN', { hour12: false }) : '—'
const frameAge = computed(() => { const time = Date.parse(visibleFrame.value?.created_at); return Number.isFinite(time) ? Math.max(0, (clock.value.getTime() - time) / 1000).toFixed(1) + ' s' : '—' })
const classLabel = d => classes.value.find(c => String(c.id) === String(d.class_id))?.label || d.class_name
const count = id => visibleFrame.value ? visibleFrame.value.detections.filter(d => String(d.class_id) === String(id)).length : '—'
const notices = computed(() => {
  const items = []
  if (checked.value && !connected.value) items.push({ tone: 'danger', title: '展示连接中断', text: error.value || '保留最后一次完整画面；它不代表当前状态。' })
  if (stream.value?.error) items.push({ tone: 'danger', title: '任务异常', text: errorText(stream.value.error) })
  if (snapshot.value?.frame?.status === 'error') items.push({ tone: 'danger', title: '本帧处理失败', text: errorText(snapshot.value.frame.error) || '不能据此判断有无目标。' })
  if (prepared.value.error) items.push({ tone: 'warning', title: '预览提示', text: prepared.value.error })
  if (prepared.value.loading) items.push({ tone: 'neutral', title: '正在准备预览', text: '图片解码完成后，同时显示对应检测框与坐标。' })
  if (!items.length) items.push({ tone: stream.value ? 'good' : 'neutral', title: stateLabel.value, text: stream.value ? '只读订阅最新完整结果；图片更新率与检测吞吐分别计量。' : '等待后台管理启动任务。' })
  return items
})
watch(() => stream.value?.session_id, () => { filter.value = ''; display.value = { frame: null, selected: null } })
onMounted(() => { clockTimer = setInterval(() => { clock.value = new Date() }, 1000) })
onBeforeUnmount(() => clearInterval(clockTimer))
</script>

<template>
  <main class="display-page industrial-display">
    <header class="industrial-header">
      <div class="industrial-brand"><span class="brand-mark" aria-hidden="true">F</span><div><strong>FACTORY DEMO</strong><small>工业视觉 · 检测展示</small></div></div>
      <div class="industrial-title"><h1>工业视觉检测展示系统</h1><p>INDUSTRIAL VISION INSPECTION</p></div>
      <div class="industrial-clock"><time>{{ timeText }}</time><span>{{ dateText }} · 本机时间</span></div>
    </header>
    <div class="display-statusbar">
      <span class="connection-badge" :class="connected ? 'good' : checked ? 'danger' : 'neutral'"><i></i>{{ connected ? '结果数据已连接' : checked ? '连接中断 · 最后结果' : '正在连接' }}</span>
      <span>最近同步 <b>{{ timeOf(lastContact) }}</b></span><span class="statusbar-task">任务 <b :title="stream?.session_id">{{ stream?.session_id?.slice(0, 8) || '—' }}</b></span>
      <a class="module-link" href="/admin.html" target="_blank" rel="noopener">后台管理 ↗</a>
    </div>
    <div class="industrial-grid">
      <aside class="industrial-left">
        <section class="panel dashboard-panel">
          <h2 class="dashboard-heading"><span>服务与任务状态</span><small>SYSTEM STATUS</small></h2>
          <div class="health-grid">
            <article><span>结果连接</span><strong :class="connected ? 'good' : checked ? 'danger' : 'neutral'">{{ connected ? '已连接' : checked ? '中断' : '检查中' }}</strong></article>
            <article><span>结果距今</span><strong class="neutral">{{ frameAge }}</strong></article>
            <article><span>当前任务</span><strong :class="stateTone">{{ stateLabel }}</strong></article>
            <article><span>运行设备</span><strong class="neutral">{{ stream?.model?.device || '—' }}</strong></article>
          </div>
          <dl class="source-info"><dt>推理引擎</dt><dd>{{ engine }}</dd><dt>模型</dt><dd>{{ stream?.model?.name || '尚未加载' }}</dd><dt>图片来源</dt><dd>{{ stream?.source_label || '—' }}</dd></dl>
          <p class="dashboard-note">展示只依赖统一协议；结果距今按本机时钟计算，不代表采集到动作延迟。</p>
        </section>
        <section class="panel dashboard-panel category-panel">
          <h2 class="dashboard-heading"><span>检测类别统计</span><small>OBJECT CLASSES</small></h2>
          <label class="display-filter">画面筛选<select v-model="filter"><option value="">全部类别</option><option v-for="c in classes" :key="c.id" :value="String(c.id)">{{ c.label || c.name }}</option></select></label>
          <div class="category-columns"><span>检测类别</span><span>当前帧</span><span>任务累计</span></div>
          <div v-for="c in classes" :key="c.id" class="category-row"><span><i :style="{ background: c.color || '#57d9e9' }"></i>{{ c.label || c.name }}</span><strong>{{ count(c.id) }}</strong><b>{{ stream?.class_counts?.[c.id] || 0 }}</b></div>
          <p v-if="!classes.length" class="dashboard-empty">模型类别尚未就绪</p>
          <p class="dashboard-note">累计值为当前任务检测框数，不是去重物体数。筛选只改变本页显示。</p>
        </section>
      </aside>
      <section class="industrial-center">
        <DetectionStage :key="stream?.session_id || 'idle'" :frame="frame" :loading="prepared.loading" :error="prepared.error" :connected="connected" :state="stream?.status" :class-filter="filter" @display-change="display = $event" />
        <details class="panel coordinate-details">
          <summary><span>当前帧坐标明细</span><span>{{ visibleFrame ? `${detections.length} 个可见目标 · FRAME ${visibleFrame.id}` : '等待画面' }}</span></summary>
          <div class="coordinate-context">原图左上角为原点，x 向右、y 向下，单位 px。任务 {{ visibleFrame?.sessionId || '—' }} / 帧 {{ visibleFrame?.id || '—' }}。</div>
          <div class="table-scroll"><table><thead><tr><th>帧内编号</th><th>类别</th><th>置信度</th><th>P1 → P2 → P3 → P4</th></tr></thead><tbody><tr v-for="d in detections" :key="d.id"><td>{{ d.id }}</td><td>{{ classLabel(d) }}</td><td>{{ (d.confidence * 100).toFixed(1) }}%</td><td class="coordinates">{{ d.polygon.map(p => `(${p.map(v => v.toFixed(1)).join(', ')})`).join(' → ') }}</td></tr><tr v-if="!detections.length"><td colspan="4">{{ prepared.loading ? '等待预览加载完成' : '当前没有可显示的检测框' }}</td></tr></tbody></table></div>
        </details>
        <div class="display-footnote"><span>HBB / OBB 原图像素坐标</span><span>只读展示 · 任务控制与历史查询在后台进行</span></div>
      </section>
      <aside class="industrial-right">
        <section class="panel dashboard-panel metrics-panel">
          <h2 class="dashboard-heading"><span>任务处理指标</span><small>RUN METRICS</small></h2>
          <div class="primary-metric"><span>已处理图片</span><strong>{{ stream?.processed ?? '—' }}<small>/ {{ !stream ? '—' : stream.total == null ? '连续流' : stream.total + ' 张' }}</small></strong></div>
          <progress v-if="stream?.total != null" :value="progress" max="100" aria-label="任务处理进度"></progress>
          <div class="result-counts"><div><span>成功</span><b class="good">{{ stream?.succeeded ?? '—' }}</b></div><div><span>失败</span><b :class="stream?.failed ? 'danger' : 'neutral'">{{ stream?.failed ?? '—' }}</b></div><div><span>当前帧目标</span><b>{{ visibleFrame?.detections.length ?? '—' }}</b></div></div>
          <div class="timing-heading">当前帧处理耗时 <small>ms</small></div>
          <dl class="timing-values"><dt>读取 / 预处理</dt><dd>{{ ms(visibleFrame?.timing_ms?.read) }} / {{ ms(visibleFrame?.timing_ms?.preprocess) }}</dd><dt>模型前向</dt><dd class="accent-value">{{ ms(visibleFrame?.timing_ms?.inference) }}</dd><dt>后处理 / 合计</dt><dd>{{ ms(visibleFrame?.timing_ms?.postprocess) }} / {{ ms(visibleFrame?.timing_ms?.total) }}</dd></dl>
          <div class="run-quantiles"><span>{{ stream?.mode === 'continuous' ? '最近窗口 P50' : '任务 P50' }} <b>{{ ms(stream?.timings?.p50_ms) }}</b> ms</span><span>P95 <b>{{ ms(stream?.timings?.p95_ms) }}</b> ms</span></div>
          <p class="dashboard-note">耗时来自后端处理统计，不含传输和页面渲染；置信度不等于准确率。</p>
        </section>
        <section class="panel dashboard-panel target-panel">
          <h2 class="dashboard-heading"><span>选中目标坐标</span><small>TARGET DETAIL</small></h2>
          <template v-if="selected"><div class="target-title"><strong>{{ classLabel(selected) }}</strong><span>#{{ selected.id }} · {{ (selected.confidence * 100).toFixed(1) }}%</span></div><div class="point-grid"><div v-for="(point, index) in selected.polygon" :key="index"><span>P{{ index + 1 }}</span><b>{{ point[0].toFixed(1) }}, {{ point[1].toFixed(1) }}</b></div></div><p class="dashboard-note">中心 {{ selected.center.map(v => v.toFixed(1)).join(', ') }} px · 角度 {{ selected.orientation_valid ? selected.angle_deg.toFixed(1) + '°' : '无有效方向' }}<br>长轴方向不等于机械臂姿态；顶点为原图像素坐标。</p></template>
          <div v-else class="target-empty"><span aria-hidden="true">⌖</span><p>点击检测框查看四点坐标</p><small>也可用 Tab 聚焦检测框，按回车选择</small></div>
        </section>
        <section class="panel dashboard-panel notices-panel">
          <h2 class="dashboard-heading"><span>当前状态提示</span><small>STATUS NOTICE</small></h2>
          <div class="notice-list"><article v-for="(notice, index) in notices" :key="index" :class="notice.tone"><i></i><div><strong>{{ notice.title }}</strong><p>{{ notice.text }}</p></div></article></div>
          <p class="dashboard-note">结果生成时间 {{ timeOf(visibleFrame?.created_at) }}。此处不保存历史日志。</p>
        </section>
      </aside>
    </div>
  </main>
</template>

