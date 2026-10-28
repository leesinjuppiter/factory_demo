<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import DetectionStage from './components/DetectionStage.vue'
import { api, download, post } from './api'
import { legacyViewInput } from './stream/contract.js'
import { usePreparedFrame } from './stream/usePreparedFrame.js'

const tab = ref('workbench')
const capabilities = ref(null)
const connected = ref(false)
const lastContact = ref(null)
const error = ref('')
const notice = ref('')
const busy = ref(false)
const currentRun = ref(null)
const currentFrame = ref(null)
const uploadedSources = ref([])
const classFilter = ref('')
const form = reactive({ source_id: 'smoke_test', engine: 'pytorch', confidence: .25, iou: .45, image_size: 640, max_det: 300, replay_fps: 1 })
const history = ref({ items: [], total: 0, page: 1, page_size: 10 })
const historyBusy = ref(false)
const historyRun = ref(null)
const historyFrames = ref({ items: [], total: 0, page: 1, page_size: 10 })
const historyFrame = ref(null)
let timer
let disposed = false
let mutationVersion = 0
let historyRequestVersion = 0

const statuses = { loading: '模型加载中', running: '正在检测', pausing: '正在暂停', paused: '已暂停', stopping: '正在停止', completed: '已完成', stopped: '已停止', failed: '任务失败', interrupted: '意外中断' }
const terminal = status => ['completed', 'stopped', 'failed', 'interrupted'].includes(status)
const active = computed(() => currentRun.value && !terminal(currentRun.value.status))
const sources = computed(() => [...(capabilities.value?.sources || []), ...uploadedSources.value])
const selectedSource = computed(() => sources.value.find(s => s.id === form.source_id))
const selectedEngine = computed(() => capabilities.value?.engines?.find(e => e.id === form.engine))
const displayRun = computed(() => tab.value === 'history' ? historyRun.value : currentRun.value)
const displayFrame = computed(() => tab.value === 'history' ? historyFrame.value : currentFrame.value)
// 配置页显示服务当前配置；工作台和历史页显示对应运行保存的模型快照。
const model = computed(() => tab.value === 'config'
  ? capabilities.value?.model || {}
  : displayRun.value?.model || capabilities.value?.model || {})
const classes = computed(() => model.value.classes || [])
const historyInput = computed(() => tab.value === 'history' ? legacyViewInput(historyFrame.value, classes.value) : null)
const historyPrepared = usePreparedFrame(historyInput, connected)
const modelDatasetNote = computed(() => model.value.name?.startsWith('factory_now') && classes.value.length === 8
  ? '当前权重 8 类，小数据集 7 类且顺序不同；本版不计算准确率。'
  : '本项目小数据集含 7 类，显示类别以权重为准；本版不计算准确率。')
const visibleDetections = computed(() => (displayFrame.value?.detections || []).filter(d => classFilter.value === '' || String(d.class_id) === classFilter.value))
const progress = computed(() => currentRun.value?.total ? Math.round(currentRun.value.processed / currentRun.value.total * 100) : 0)
const number = (v, digits = 1) => Number.isFinite(Number(v)) && v != null ? Number(v).toFixed(digits) : '—'
const date = v => v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '—'
const statusName = v => statuses[v] || v || '尚未运行'
const message = e => e.name === 'TimeoutError' ? '请求超时，请检查服务状态后重试。' : e.message === 'Failed to fetch' ? '无法连接本地服务，请检查启动窗口。' : e.message
const category = d => classes.value.find(c => c.id === d.class_id)?.label || d.class_name
const frameCount = id => (displayFrame.value?.detections || []).filter(d => d.class_id === id).length

async function refreshCapabilities(initial = false) {
  capabilities.value = await api('/capabilities')
  if (initial && capabilities.value.defaults) {
    for (const key of Object.keys(form)) if (capabilities.value.defaults[key] != null) form[key] = capabilities.value.defaults[key]
  }
}

// 快照轮询使用递归计时，前一个请求完成后才发起下一个，避免慢机器堆积请求。
async function poll() {
  const version = mutationVersion
  try {
    const snapshot = await api('/status')
    if (disposed) return
    if (version === mutationVersion) {
      currentRun.value = snapshot.run
      currentFrame.value = snapshot.frame
    }
    connected.value = true
    lastContact.value = new Date()
    if (!capabilities.value) await refreshCapabilities(true)
  } catch { connected.value = false }
  finally { if (!disposed) timer = setTimeout(poll, 500) }
}

async function action(fn) {
  if (busy.value) return
  mutationVersion++
  busy.value = true
  error.value = ''
  notice.value = ''
  try { await fn() } catch (e) { error.value = message(e) } finally {
    mutationVersion++
    busy.value = false
  }
}

async function startRun() {
  await action(async () => {
    currentRun.value = await post('/runs', { ...form })
    currentFrame.value = null
    classFilter.value = ''
    notice.value = '已创建新任务。关闭此页面不会停止推理。'
  })
}

async function control(actionName) {
  if (!currentRun.value) return
  await action(async () => { currentRun.value = await post(`/runs/${currentRun.value.id}/control`, { action: actionName }) })
}

async function upload(event) {
  const file = event.target.files?.[0]
  if (!file) return
  await action(async () => {
    if (!/\.(jpe?g|png|bmp)$/i.test(file.name)) throw new Error('请选择 JPG、JPEG、PNG 或 BMP 图片。')
    if (file.size > (capabilities.value?.limits?.max_file_bytes || 20 * 1024 * 1024)) throw new Error('图片超过 20 MiB 限制，请选择较小的图片。')
    const payload = new FormData()
    payload.append('file', file)
    const result = await api('/uploads', { method: 'POST', body: payload })
    uploadedSources.value.push({ id: result.source_id, label: result.label, count: 1 })
    form.source_id = result.source_id
    notice.value = `已添加 ${result.label}，点击“开始检测”运行。`
  })
  event.target.value = ''
}

async function loadHistory(page = 1) {
  const version = ++historyRequestVersion
  historyBusy.value = true
  error.value = ''
  try {
    const result = await api(`/runs?page=${page}&page_size=10`)
    if (version === historyRequestVersion) history.value = result
  }
  catch (e) { if (version === historyRequestVersion) error.value = message(e) }
  finally { if (version === historyRequestVersion) historyBusy.value = false }
}

async function openHistory(run, page = 1) {
  const version = ++historyRequestVersion
  historyBusy.value = true
  error.value = ''
  try {
    const [detail, frames] = await Promise.all([api(`/runs/${run.id}`), api(`/runs/${run.id}/frames?page=${page}&page_size=10`)])
    if (version !== historyRequestVersion) return
    historyRun.value = detail
    historyFrames.value = frames
    historyFrame.value = frames.items[0] || null
    classFilter.value = ''
  } catch (e) { if (version === historyRequestVersion) error.value = message(e) }
  finally { if (version === historyRequestVersion) historyBusy.value = false }
}

async function selectTab(value) {
  historyRequestVersion++
  historyBusy.value = false
  tab.value = value
  classFilter.value = ''
  error.value = ''
  notice.value = ''
  if (value === 'history') await loadHistory()
  if (value === 'config') await action(() => refreshCapabilities())
}

async function exportRun(run, format) {
  if (!run) return
  await action(() => download(`/api/runs/${run.id}/export?format=${format}`, `factory-${run.id}.${format}`))
}

async function exportImage() {
  const frame = displayFrame.value
  if (frame) await action(() => download(frame.annotated_url, `${frame.name.replace(/\.[^.]+$/, '')}-detections.png`))
}

onMounted(poll)
onBeforeUnmount(() => { disposed = true; clearTimeout(timer) })
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <a class="brand" href="#" @click.prevent="selectTab('workbench')"><span class="brand-symbol">F<span></span></span><span>FACTORY<b>视觉任务管理</b></span></a>
      <div class="nav-label">工作空间</div>
      <a class="module-link" href="/" target="_blank" rel="noopener">打开检测展示 ↗</a>
      <nav aria-label="后台导航">
        <button :class="{ selected: tab === 'workbench' }" @click="selectTab('workbench')"><span>▣</span>任务管理</button>
        <button :class="{ selected: tab === 'history' }" @click="selectTab('history')"><span>≡</span>历史记录</button>
        <button :class="{ selected: tab === 'config' }" @click="selectTab('config')"><span>⚙</span>运行配置</button>
      </nav>
      <div class="sidebar-bottom"><span class="small-tag">LOCAL EDITION / V1.3</span><p>统一结果协议<br>真实推理 · 本机运行</p><div class="connection"><i :class="{ online: connected }"></i>{{ connected ? '服务已连接' : '服务连接中断' }}</div></div>
    </aside>

    <main class="main-content">
      <header class="page-header">
        <div><span class="section-kicker">FACTORY DEMO / {{ tab === 'workbench' ? 'INSPECTION' : tab === 'history' ? 'RUN HISTORY' : 'CONFIGURATION' }}</span><h1>{{ tab === 'workbench' ? '任务管理' : tab === 'history' ? '历史记录' : '运行配置' }}</h1><p>{{ tab === 'workbench' ? '配置数据源和参数，创建、暂停或停止后台任务。' : tab === 'history' ? '查看运行配置、逐图结果与导出记录。' : '了解当前模型、数据来源与服务能力。' }}</p></div>
        <div class="header-status"><span class="status-pill" :class="connected ? 'good' : 'warning'"><i></i>{{ connected ? '本地服务在线' : '连接已断开' }}</span><small>{{ lastContact ? `最近通信 ${lastContact.toLocaleTimeString('zh-CN', { hour12: false })}` : '等待 API 服务' }}</small></div>
      </header>

      <div v-if="!connected" class="alert warning" role="status">无法获取最新运行状态，正在自动重连。已有结果保留；连接恢复前不接受任务控制。</div>
      <div v-if="error" class="alert danger" role="alert"><span>{{ error }}</span><button class="text-button" @click="error = ''" aria-label="关闭错误提示">×</button></div>
      <div v-if="notice" class="alert success" role="status">{{ notice }}</div>

      <template v-if="tab === 'workbench'">
        <div class="metric-strip">
          <article><span>运行状态</span><strong class="state-text" :class="currentRun?.status">{{ statusName(currentRun?.status) }}</strong><small>{{ currentRun ? `${currentRun.id.slice(0, 8)} · ${currentRun.source_label}` : '选择来源后开始' }}</small></article>
          <article><span>已处理图片</span><strong>{{ currentRun?.processed ?? 0 }}<em>/ {{ currentRun?.total ?? '连续流' }}</em></strong><small>成功 {{ currentRun?.succeeded ?? 0 }} · 失败 {{ currentRun?.failed ?? 0 }}</small></article>
          <article><span>累计检测实例</span><strong>{{ currentRun?.detection_count ?? 0 }}<em>个</em></strong><small>逐图累加，不作跨帧去重</small></article>
          <article><span>最近完整处理耗时</span><strong>{{ number(currentFrame?.timing_ms?.total) }}<em>ms</em></strong><small>读取 + 预处理 + 推理 + 后处理</small></article>
        </div>

        <div class="work-grid">
          <div class="work-main">

            <section class="panel run-controls">
              <div class="progress-row"><span>{{ currentRun?.source_label || '未开始运行' }}</span><span>{{ currentRun?.total == null ? '连续流' : progress + '%' }}</span></div><progress v-if="currentRun?.total != null" :value="currentRun?.processed || 0" :max="currentRun?.total || 1"></progress>
              <div class="control-row">
                <button v-if="currentRun?.status === 'paused'" class="primary" :disabled="busy || !connected" @click="control('resume')">继续检测</button>
                <button v-else :disabled="busy || !connected || currentRun?.status !== 'running'" @click="control('pause')">{{ currentRun?.status === 'pausing' ? '等待当前帧完成…' : '暂停' }}</button>
                <button :disabled="busy || !connected || !active || currentRun?.status === 'stopping'" @click="control('stop')">{{ currentRun?.status === 'stopping' ? '正在停止…' : '停止任务' }}</button>
                <span class="control-note">暂停 / 停止在当前帧处理完成后生效</span>
              </div>
              <p v-if="currentRun?.error" class="inline-error">{{ currentRun.error }}</p>
              <p v-if="currentRun?.status === 'completed' && currentRun.failed" class="inline-error">任务已结束，其中 {{ currentRun.failed }} 张处理失败。请在历史记录中查看原因。</p>
            </section>
          </div>

          <aside class="config-column">
            <form class="panel settings" @submit.prevent="startRun">
              <div class="panel-title"><h2>检测任务</h2><span class="small-tag">NEW RUN</span></div>
              <fieldset :disabled="!!active || busy || !connected || !capabilities">
                <label>图片来源<select v-model="form.source_id" required><option v-for="s in sources" :key="s.id" :value="s.id">{{ s.label }} · {{ s.mode === 'continuous' ? '持续文件源' : s.count + ' 张' }}</option></select></label>
                <label class="upload-button">＋ 上传单张图片<input type="file" accept=".jpg,.jpeg,.png,.bmp" @change="upload"></label>
                <label>推理引擎<select v-model="form.engine"><option v-for="engine in capabilities?.engines || []" :key="engine.id" :value="engine.id" :disabled="!engine.available">{{ engine.label }}{{ engine.available ? '' : '（不可用）' }}</option></select></label>
                <p v-if="selectedEngine && !selectedEngine.available" class="inline-error">{{ selectedEngine.reason }}</p>
                <p v-if="selectedSource?.error" class="inline-error">{{ selectedSource.error }}</p>
                <div class="field-pair"><label>置信度阈值<input type="number" v-model.number="form.confidence" min="0.001" max="1" step="0.001" required></label><label>NMS IoU<input type="number" v-model.number="form.iou" min="0.01" max="1" step="0.01" required></label></div>
                <div class="field-pair"><label>输入尺寸<input type="number" v-model.number="form.image_size" min="320" max="1280" step="32" required></label><label>每图最多目标<input type="number" v-model.number="form.max_det" min="1" max="1000" step="1" required></label></div>
                <label v-if="selectedSource?.mode !== 'continuous'">目标回放速度 <span class="muted">张 / 秒</span><input type="number" v-model.number="form.replay_fps" min="0.1" :max="capabilities?.limits?.replay_fps_max || 10" step="0.1" required></label>
                <p class="field-hint">实际速度受推理耗时限制。以上参数在创建任务时固定。</p>
              </fieldset>
              <button class="primary start-button" type="submit" :disabled="!!active || busy || !connected || !selectedEngine?.available || !selectedSource || (selectedSource.mode !== 'continuous' && selectedSource.count === 0)">{{ active ? '任务进行中' : busy ? '正在提交…' : currentRun ? '按当前配置重新运行' : '开始检测' }}<span>→</span></button>
              <p class="field-hint">{{ selectedSource?.mode === 'continuous' ? '持续读取已发布文件；空目录也可启动，等待相机或模拟器发布。暂停检测不会停止拍照。' : '一次运行处理来源中的每张图片一遍。重新运行会创建新记录。' }}</p>
            </form>
            <section class="panel model-summary"><h2>当前模型</h2><dl><dt>权重</dt><dd :title="model.path">{{ model.name || '等待加载' }}</dd><dt>框类型 / 设备</dt><dd>{{ model.box_type?.toUpperCase() || '—' }} / {{ model.device || '—' }}</dd><dt>推理引擎</dt><dd>{{ currentRun?.config?.engine || form.engine }}</dd><dt>类别数</dt><dd>{{ classes.length || '加载后确认' }}</dd></dl><p class="model-boundary-note">{{ modelDatasetNote }}</p><p>置信度表示模型评分，不等于检测准确率。</p></section>
          </aside>
        </div>
      </template>

      <template v-if="tab === 'history'">
        <section class="panel history-panel">
          <div class="panel-title"><h2>运行批次 <span class="count-label">{{ history.total }}</span></h2><button :disabled="historyBusy" @click="loadHistory(history.page)">刷新记录</button></div>
          <div class="table-scroll"><table><thead><tr><th>运行 / 创建时间</th><th>图片来源</th><th>状态</th><th>成功 / 失败 / 总数</th><th>检测实例</th><th>操作</th></tr></thead><tbody><tr v-for="run in history.items" :key="run.id" :class="{ 'selected-row': historyRun?.id === run.id }"><td><code>{{ run.id.slice(0, 8) }}</code><small class="cell-secondary">{{ date(run.created_at) }}</small></td><td>{{ run.source_label }}</td><td><span class="status-pill" :class="run.status === 'failed' || run.status === 'interrupted' ? 'warning' : ''">{{ statusName(run.status) }}</span></td><td>{{ run.succeeded }} / {{ run.failed }} / {{ run.total ?? '连续流' }}</td><td>{{ run.detection_count }}</td><td><button class="text-button" :disabled="historyBusy" @click="openHistory(run)">查看结果 →</button></td></tr><tr v-if="!history.items.length"><td colspan="6" class="table-empty">{{ historyBusy ? '正在加载记录…' : '暂无历史记录，先在工作台完成一次检测。' }}</td></tr></tbody></table></div>
          <div class="pagination"><span>共 {{ history.total }} 个任务</span><button :disabled="historyBusy || history.page <= 1" @click="loadHistory(history.page - 1)">上一页</button><span>{{ history.page }} / {{ Math.max(1, Math.ceil(history.total / history.page_size)) }}</span><button :disabled="historyBusy || history.page * history.page_size >= history.total" @click="loadHistory(history.page + 1)">下一页</button></div>
        </section>
        <template v-if="historyRun">
          <section class="panel history-detail"><div class="panel-title"><div><h2>任务详情 · {{ historyRun.id.slice(0, 8) }}</h2><p>{{ historyRun.source_label }} · {{ statusName(historyRun.status) }}</p></div><div class="button-group"><button :disabled="busy || !terminal(historyRun.status)" @click="exportRun(historyRun, 'json')">导出 JSON</button><button :disabled="busy || !terminal(historyRun.status)" @click="exportRun(historyRun, 'csv')">导出 CSV</button></div></div><p class="detail-meta">创建 {{ date(historyRun.created_at) }}　结束 {{ date(historyRun.finished_at) }}　P50 {{ number(historyRun.timings?.p50_ms) }} ms　P95 {{ number(historyRun.timings?.p95_ms) }} ms</p><p v-if="historyRun.error" class="inline-error">{{ historyRun.error }}</p><details><summary>本次运行配置与模型信息</summary><pre>{{ JSON.stringify({ config: historyRun.config, model: historyRun.model }, null, 2) }}</pre></details></section>
          <div class="history-view-grid"><DetectionStage :allow-download="true" :frame="historyPrepared.frame" :loading="historyPrepared.loading" :error="historyPrepared.error" :historical="true" :connected="connected" :state="historyRun.status" :class-filter="classFilter" @download="exportImage" /><section class="panel frame-list"><div class="panel-title"><h2>逐图结果</h2><span>{{ historyFrames.total }} 张</span></div><button v-for="frame in historyFrames.items" :key="frame.id" :class="{ selected: historyFrame?.id === frame.id }" @click="historyFrame = frame"><span class="frame-id">{{ String(frame.id).padStart(3, '0') }}</span><span class="frame-list-name">{{ frame.name }}<small>{{ frame.status === 'error' ? '处理失败' : `${frame.detections.length} 个目标 · ${number(frame.timing_ms?.total)} ms` }}</small></span><span v-if="frame.status === 'error'" class="error-dot">!</span></button><p v-if="!historyFrames.items.length" class="table-empty">没有已保存的图片结果。</p><div class="pagination"><button :disabled="historyBusy || historyFrames.page <= 1" @click="openHistory(historyRun, historyFrames.page - 1)">上一页</button><span>{{ historyFrames.page }}</span><button :disabled="historyBusy || historyFrames.page * historyFrames.page_size >= historyFrames.total" @click="openHistory(historyRun, historyFrames.page + 1)">下一页</button></div></section></div>
        </template>
      </template>

      <section v-if="tab !== 'config' && displayRun" class="panel results-panel">
        <div class="panel-title"><div><h2>检测结果 <span class="count-label">{{ visibleDetections.length }}</span></h2><p>当前图片的预测实例；筛选只影响显示，不修改统计与导出。</p></div><label class="filter-label">类别筛选<select v-model="classFilter"><option value="">全部类别</option><option v-for="item in classes" :key="item.id" :value="String(item.id)">{{ item.label || item.name }}</option></select></label></div>
        <div class="results-grid"><div class="table-scroll detection-table"><table><thead><tr><th>图内序号</th><th>类别</th><th>置信度</th><th>四点坐标 / 原图像素</th></tr></thead><tbody><tr v-for="d in visibleDetections" :key="d.id"><td>{{ d.id }}</td><td><span class="class-dot" :style="{ background: classes.find(c => c.id === d.class_id)?.color || '#278478' }"></span>{{ category(d) }}</td><td>{{ (d.confidence * 100).toFixed(1) }}%</td><td class="coordinates">{{ d.polygon.map(p => `(${p.map(v => Number(v).toFixed(1)).join(', ')})`).join(' · ') }}</td></tr><tr v-if="!visibleDetections.length"><td colspan="4" class="table-empty">{{ !displayFrame ? '等待图片结果' : displayFrame.status === 'error' ? '本图处理失败，不能据此判断有无目标' : '当前图片或筛选条件下没有检测目标' }}</td></tr></tbody></table></div><div class="class-summary"><h3>类别计数</h3><div class="summary-label"><span>类别</span><span>当前 / 本次累计</span></div><div v-for="item in classes" :key="item.id"><span><i class="class-dot" :style="{ background: item.color }"></i>{{ item.label || item.name }}</span><strong>{{ frameCount(item.id) }} <em>/ {{ displayRun.class_counts?.[item.id] || 0 }}</em></strong></div><p v-if="!classes.length">模型加载后显示类别。</p></div></div>
        <div class="timing-strip"><span>本图耗时</span><span>读取 <b>{{ number(displayFrame?.timing_ms?.read) }}</b> ms</span><span>预处理 <b>{{ number(displayFrame?.timing_ms?.preprocess) }}</b> ms</span><span>推理 <b>{{ number(displayFrame?.timing_ms?.inference) }}</b> ms</span><span>后处理 <b>{{ number(displayFrame?.timing_ms?.postprocess) }}</b> ms</span></div>
        <div class="run-timing-summary"><h3>本次运行统计</h3><div class="table-scroll"><table><thead><tr><th>平均处理耗时</th><th>P50 处理耗时</th><th>P95 处理耗时</th><th>处理速度</th></tr></thead><tbody><tr><td>{{ number(displayRun.timings?.mean_ms) }} ms</td><td>{{ number(displayRun.timings?.p50_ms) }} ms</td><td>{{ number(displayRun.timings?.p95_ms) }} ms</td><td>{{ number(displayRun.timings?.fps, 2) }} FPS</td></tr></tbody></table></div><p>基于本次已成功处理图片的读取、预处理、推理与后处理耗时；不含落盘、页面显示和回放等待。处理 FPS 为 1000 ÷ 平均耗时，不是目标回放速度或端到端吞吐。</p></div>
      </section>

      <template v-if="tab === 'config'">
        <section class="panel info-panel"><div class="panel-title"><h2>推理引擎</h2><span class="small-tag">统一协议 {{ capabilities?.protocol_version || '—' }}</span></div><div class="engine-list"><article v-for="engine in capabilities?.engines || []" :key="engine.id"><div class="engine-icon">{{ engine.id === 'pytorch' ? 'PT' : engine.id === 'openvino' ? 'OV' : 'TR' }}</div><div><h3>{{ engine.label }}</h3><p>{{ engine.reason || '可用于当前任务；实际模型加载结果以运行记录为准。' }}</p></div><span class="status-pill" :class="engine.available ? 'good' : ''">{{ engine.available ? '已接入' : '未接入' }}</span></article></div></section>
        <div class="config-info-grid"><section class="panel info-panel"><h2>数据来源</h2><p>只开放服务端预配置的目录及本次上传的图片。自定义目录需修改本地配置后重启服务。</p><table><thead><tr><th>来源</th><th>图片数</th></tr></thead><tbody><tr v-for="source in capabilities?.sources || []" :key="source.id"><td>{{ source.label }}<small class="cell-secondary">{{ source.id }}</small></td><td>{{ source.mode === 'continuous' ? '持续读取' : source.count }}</td></tr></tbody></table><p>小数据集用于流程检查。train / val / test 保持原归属，不作为检测效果结论。</p></section><section class="panel info-panel"><h2>模型信息</h2><dl><dt>名称</dt><dd>{{ model.name || '首次运行后加载' }}</dd><dt>位置</dt><dd class="path-text">{{ model.path || '—' }}</dd><dt>设备</dt><dd>{{ model.device || '—' }}</dd><dt>SHA-256</dt><dd class="path-text">{{ model.sha256 || '首次运行后记录' }}</dd></dl><p>本版固定使用配置中的权重。切换权重需修改配置并重启，已保存记录不变。</p></section></div>
        <section class="panel info-panel"><h2>运行边界</h2><ul class="boundary-list"><li>本机单进程、单活动任务。所有浏览器共享同一个运行状态。</li><li>关闭页面不会结束任务；暂停 / 停止等待当前图片处理结束。</li><li>实时画面按最新快照刷新，可能跳过中间画面；已处理结果保存在 PostgreSQL。</li><li>重新运行产生独立记录；当前版本不提供标注、训练和跨帧跟踪。</li><li>置信度是模型评分，累计实例数不是去重实物数，处理速度不是产线吞吐。</li></ul><details v-if="capabilities?.limits"><summary>服务端资源与参数限制</summary><pre>{{ JSON.stringify(capabilities.limits, null, 2) }}</pre></details></section>
      </template>

      <footer>Factory Demo <span>·</span> 本地工业视觉验证平台 <span>·</span> 所有结果以实际推理和保存记录为准</footer>
    </main>
  </div>
</template>

