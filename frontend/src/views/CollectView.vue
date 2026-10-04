<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, errMsg, collectBatchStream, collectFilesStream } from '../api.js'
import { planCollectionBatches } from '../collectionBatches.js'

const props = defineProps({
  meta: { type: Object, required: true },
  aiSettings: { type: Object, required: true },
})
const conferences = computed(() => props.meta?.conferences || [])
const llm = computed(() => props.aiSettings.llm || {})
const conferenceQuery = ref('')
const filteredConferences = computed(() => {
  const query = conferenceQuery.value.trim().toLocaleLowerCase('en-US')
  if (!query) return conferences.value
  return conferences.value.filter(conference => {
    const aliases = Array.isArray(conference.aliases) ? conference.aliases : []
    const searchable = [
      conference.acronym,
      conference.full_name,
      conference.area,
      conference.rank,
      ...aliases,
    ].filter(Boolean).join(' ').toLocaleLowerCase('en-US')
    return searchable.includes(query)
  })
})

function filterConferences(query) {
  conferenceQuery.value = query || ''
}

function conferenceLabel(conference) {
  return `${conference.acronym} · CCF-${conference.rank} · ${conference.area}`
}

function onConferenceDropdown(visible) {
  if (!visible) conferenceQuery.value = ''
}

const today = new Date().getFullYear()
const stats = ref(null)
const form = reactive({
  conference_id: null,
  year: today,
  max_pages: 4,
})
const batch = reactive({
  conference_ids: [], years: String(today), strategy: 'auto', max_pages: 4,
  award_types: ['best_paper', 'best_student_paper'],
})
const batchRunning = ref(false)
const batchResult = ref(null)
const batchTasks = ref([])
const PLAN_KEY = 'ccf-awards-collection-plan'
const batchPlan = ref(null)
const nextBatchIndex = ref(0)
const planProgress = reactive({ completed: 0, failed: 0 })
const batchUncertain = ref(false)
const draftPlan = computed(() => {
  try { return planCollectionBatches(batch.conference_ids, batch.years) }
  catch { return null }
})
const currentChunk = computed(() => batchPlan.value
  ? batchPlan.value.chunks[nextBatchIndex.value] || null
  : draftPlan.value?.chunks[0] || null)
const currentStrategy = computed(() => batchPlan.value?.strategy || batch.strategy)
const totalTaskCount = computed(() => batchPlan.value?.totalTasks || draftPlan.value?.totalTasks || 0)
const totalBatchCount = computed(() => batchPlan.value?.chunks.length || draftPlan.value?.chunks.length || 0)
const planFinished = computed(() => !!batchPlan.value && nextBatchIndex.value >= batchPlan.value.chunks.length)
function savePlanState(inFlight = false) {
  try {
    if (!batchPlan.value) sessionStorage.removeItem(PLAN_KEY)
    else sessionStorage.setItem(PLAN_KEY, JSON.stringify({
      version: 1,
      plan: batchPlan.value, nextBatchIndex: nextBatchIndex.value,
      progress: { ...planProgress }, inFlight,
    }))
  } catch { /* Browser privacy settings may disable session storage. */ }
}
function restorePlanState() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(PLAN_KEY) || 'null')
    if (saved?.version !== 1 || !saved.plan || !Array.isArray(saved.plan.chunks) ||
        !Array.isArray(saved.plan.conference_ids) || !Array.isArray(saved.plan.award_types) ||
        !['auto', 'urls'].includes(saved.plan.strategy) ||
        !Number.isInteger(saved.plan.max_pages) || saved.plan.max_pages < 1 || saved.plan.max_pages > 20 ||
        !Number.isInteger(saved.nextBatchIndex) || saved.nextBatchIndex < 0 ||
        saved.nextBatchIndex > saved.plan.chunks.length ||
        saved.plan.chunks.some(chunk => !Array.isArray(chunk.conference_ids) ||
          !Array.isArray(chunk.yearNumbers) || !chunk.yearNumbers.length ||
          chunk.yearNumbers.length > 20 || chunk.count !== chunk.conference_ids.length * chunk.yearNumbers.length ||
          chunk.count < 1 || chunk.count > 100)) return
    batchPlan.value = saved.plan
    nextBatchIndex.value = saved.nextBatchIndex
    planProgress.completed = saved.progress?.completed || 0
    planProgress.failed = saved.progress?.failed || 0
    batchUncertain.value = !!saved.inFlight
    batch.conference_ids = [...saved.plan.conference_ids]
    batch.years = saved.plan.yearText
    batch.strategy = saved.plan.strategy
    batch.max_pages = saved.plan.max_pages
    batch.award_types = [...saved.plan.award_types]
  } catch { /* Ignore a stale or unavailable session record. */ }
}
function refreshPlanState() {
  restorePlanState()
  loadRuns()
  if (batchUncertain.value) ElMessage.info('此批仍未确认结束；请核对运行日志，避免重复调用')
}
async function resetBatchPlan() {
  if (batchRunning.value) return
  if (batchPlan.value && !planFinished.value) {
    try {
      await ElMessageBox.confirm('这会放弃尚未执行的批次；已完成的记录和运行日志不会删除。确定重新选择吗？',
        '重新选择目标', { type: 'warning' })
    } catch { return }
  }
  batchPlan.value = null
  nextBatchIndex.value = 0
  planProgress.completed = 0
  planProgress.failed = 0
  batchUncertain.value = false
  batchResult.value = null
  batchTasks.value = []
  savePlanState()
}
const savedSeeds = ref([])
const seedDrafts = reactive({})
const seedLoading = ref(false)
const savingSeed = ref('')
const seedError = ref('')
let seedRequestId = 0
const seedKey = (cid, year) => `${cid}:${year}`
async function loadSelectedSeeds() {
  const requestId = ++seedRequestId
  savedSeeds.value = []
  seedError.value = ''
  seedLoading.value = false
  const chunk = currentChunk.value
  if (currentStrategy.value !== 'urls' || !chunk) return
  seedLoading.value = true
  try {
    const res = await api.lookupSeeds(chunk.conference_ids, chunk.yearNumbers)
    if (requestId === seedRequestId) savedSeeds.value = res.items || []
  } catch (e) {
    if (requestId === seedRequestId) seedError.value = errMsg(e)
  } finally {
    if (requestId === seedRequestId) seedLoading.value = false
  }
}
watch([currentStrategy, currentChunk], loadSelectedSeeds)

async function saveTargetSeed(target) {
  const key = seedKey(target.conference_id, target.year)
  const urls = [...new Set((seedDrafts[key] || '').split(/\r?\n/).map(url => url.trim()).filter(Boolean))]
  if (!urls.length) { ElMessage.warning('请先填写要保存的网址，每行一个'); return }
  savingSeed.value = key
  try {
    for (const url of urls) {
      await api.addSeed({ conference_id: target.conference_id, year: target.year, url })
    }
    seedDrafts[key] = ''
    await loadSelectedSeeds()
    await loadStats()
    ElMessage.success(`${target.conference_id} ${target.year}：已保存 ${urls.length} 个网址`)
  } catch (e) { ElMessage.error(errMsg(e)) }
  finally { savingSeed.value = '' }
}
const batchTokenTotals = computed(() => batchTasks.value.reduce((total, task) => {
  const tokens = tokenTotals(task)
  total.search += tokens.searchTokens || 0
  total.extraction += tokens.extractionTokens || 0
  return total
}, { search: 0, extraction: 0 }))
function updateBatchTask(task) {
  const index = batchTasks.value.findIndex(item => item.conference_id === task.conference_id && item.year === task.year)
  if (index < 0) batchTasks.value.push(task)
  else batchTasks.value[index] = task
}
async function runBatch() {
  if (running.value || batchRunning.value) return
  if (batchUncertain.value) restorePlanState()
  if (planFinished.value) { ElMessage.info('所有批次已完成；如需重新采集，请先重新选择目标'); return }
  let plan = batchPlan.value
  if (!plan) {
    if (!batch.award_types.length) { ElMessage.warning('请至少选择一种奖项'); return }
    if (!Number.isInteger(batch.max_pages) || batch.max_pages < 1 || batch.max_pages > 20) {
      ElMessage.warning('每项最多页面应为 1–20'); return
    }
    try {
      const { chunks, totalTasks } = planCollectionBatches(batch.conference_ids, batch.years)
      plan = {
        conference_ids: [...batch.conference_ids], yearText: batch.years,
        strategy: batch.strategy, max_pages: batch.max_pages,
        award_types: [...batch.award_types], chunks, totalTasks,
      }
    } catch (e) { ElMessage.warning(e.message); return }
  }
  const chunk = plan.chunks[nextBatchIndex.value]
  if (!chunk) return
  if (plan.strategy === 'urls') {
    await loadSelectedSeeds()
    if (seedError.value) { ElMessage.warning(seedError.value); return }
    if (savedSeeds.value.length !== chunk.count) { ElMessage.warning('未能完整读取本批已保存网址，请刷新后再试'); return }
    const missing = savedSeeds.value.filter(item => !item.urls.length)
    if (missing.length) {
      ElMessage.warning(`本批有 ${missing.length} 个会议年度尚未保存网址，请先在下方添加入口`)
      return
    }
  }
  if (!llm.value.api_key) { ElMessage.warning('请先在“LLM 连接”中填写当前账户的 API Key'); return }
  if (batchUncertain.value) {
    try {
      await ElMessageBox.confirm('上一批连接曾中断，可能已有部分任务在服务器完成。请先查看运行日志；重试本批可能产生重复调用及费用。仍要重试吗？',
        '确认重试', { type: 'warning', confirmButtonText: '仍要重试', cancelButtonText: '取消' })
    } catch { return }
  }
  try {
    const account = llm.value.provider === 'deepseek' && (llm.value.base_url || 'https://api.deepseek.com').includes('api.deepseek.com')
      ? '当前 DeepSeek Key（搜索走 Anthropic 兼容接口）' : `当前 ${llm.value.provider || 'LLM'} 连接`
    await ElMessageBox.confirm(`计划共 ${plan.totalTasks} 项，分 ${plan.chunks.length} 批。本次只执行第 ${nextBatchIndex.value + 1} 批的 ${chunk.count} 项（每项最多 ${plan.max_pages} 页）；完成后不会自动开始下一批。搜索与提取使用${account}，可能产生 Token 费用。确定开始本批吗？`,
      '逐批确认采集', { type: 'warning', confirmButtonText: '开始本批', cancelButtonText: '取消' })
  } catch { return }
  if (!batchPlan.value) batchPlan.value = plan
  batchUncertain.value = false
  savePlanState(true)
  batchRunning.value = true
  batchResult.value = null
  batchTasks.value = []
  logLines.value = []
  try {
    batchResult.value = await collectBatchStream({
      conference_ids: chunk.conference_ids, years: chunk.years,
      strategy: plan.strategy, max_pages: plan.max_pages,
      award_types: plan.award_types, llm: { ...llm.value },
    }, pushLog, updateBatchTask)
    planProgress.completed += batchResult.value.completed
    planProgress.failed += batchResult.value.failed
    nextBatchIndex.value++
    savePlanState()
    ElMessage.success(`本批结束：完成 ${batchResult.value.completed}，失败 ${batchResult.value.failed}。${planFinished.value ? '全部批次已结束。' : '下一批需再次确认。'}`)
    await loadRuns()
  } catch (e) {
    batchUncertain.value = true
    savePlanState(true)
    ElMessage.error(`${errMsg(e)}；本批状态可能不确定，请核对运行日志后再重试`)
  }
  finally { batchRunning.value = false }
}
async function exportBatchPapers() {
  const ids = batchResult.value?.record_ids || []
  if (!ids.length) return
  try {
    const blob = await api.exportBatchCsv(ids)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'ccf-awards-batch.csv'
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (e) { ElMessage.error(errMsg(e)) }
}
const running = ref(false)
const result = ref(null)
const logLines = ref([])
const logBox = ref(null)
const runHistory = ref([])
const historyLoading = ref(false)
const historyError = ref('')
const historyTotal = ref(0)
const historyDates = ref([])
const historyConference = ref('')
const historyStatus = ref('')
const deletingRuns = ref(false)
let historyTimer
let historyRequest = 0

function runFilters() {
  const filters = {}
  if (historyDates.value?.length === 2) {
    filters.started_from = new Date(Number(historyDates.value[0])).toISOString()
    filters.started_to = new Date(Number(historyDates.value[1])).toISOString()
  }
  if (historyConference.value) filters.conference_id = historyConference.value
  if (historyStatus.value) filters.status = historyStatus.value
  return filters
}

// 文件上传
const fileForm = reactive({ award_file: null, award_url: '', metadata_file: null, metadata_url: '' })

async function loadStats() {
  try { stats.value = await api.seedStats() } catch (e) { /* 忽略 */ }
}

async function loadRuns(silent = false) {
  const request = ++historyRequest
  if (!silent) historyLoading.value = true
  try {
    const res = await api.runs(runFilters())
    if (request !== historyRequest) return
    runHistory.value = res.runs || []
    historyTotal.value = res.total || 0
    historyError.value = ''
  } catch (e) {
    if (request === historyRequest) historyError.value = errMsg(e)
  } finally {
    if (request === historyRequest) historyLoading.value = false
  }
}

function exportRuns(scope = 'all') {
  const link = document.createElement('a')
  link.href = api.runExportUrl({ ...runFilters(), ...(scope === 'recent' ? { limit: 50 } : {}) })
  link.download = ''
  document.body.appendChild(link)
  link.click()
  link.remove()
}

async function deleteRunRange() {
  const filters = runFilters()
  if (!filters.started_from || !filters.started_to) {
    ElMessage.warning('请先选择完整的开始时间范围，再删除日志')
    return
  }
  deletingRuns.value = true
  try {
    const preview = await api.runDeletionPreview(filters)
    if (!preview.count) {
      ElMessage.info('该范围内没有可删除的已结束任务日志')
      return
    }
    await ElMessageBox.confirm(
      `将移除 ${preview.count} 条匹配的已结束任务日志。不会删除获奖论文或正在运行的任务。建议先导出 CSV 备份。`,
      '确认删除日志', { type: 'warning', confirmButtonText: '删除日志', cancelButtonText: '取消' }
    )
    const result = await api.deleteRuns({ ...filters, expected_count: preview.count, through_id: preview.through_id })
    ElMessage.success(`已移除 ${result.deleted} 条日志`)
    await loadRuns()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(errMsg(e))
  } finally {
    deletingRuns.value = false
  }
}

watch([historyDates, historyConference, historyStatus], () => loadRuns())

function refreshVisibleRuns() {
  if (document.visibilityState === 'visible' && !historyLoading.value && !deletingRuns.value) loadRuns(true)
}

onMounted(() => {
  restorePlanState()
  loadStats()
  loadRuns()
  historyTimer = window.setInterval(refreshVisibleRuns, 3000)
  document.addEventListener('visibilitychange', refreshVisibleRuns)
})

onUnmounted(() => {
  window.clearInterval(historyTimer)
  document.removeEventListener('visibilitychange', refreshVisibleRuns)
  historyRequest++
})

function tokenTotals(details = {}) {
  const usage = details.token_usage || {}
  const searchTokens = usage.search?.total_tokens
  const extractionTokens = usage.extraction?.total_tokens
  const known = [searchTokens, extractionTokens].filter(Number.isInteger)
  const totalTokens = Number.isInteger(details.total_tokens)
    ? details.total_tokens
    : (known.length ? known.reduce((sum, value) => sum + value, 0) : null)
  return { searchTokens, extractionTokens, totalTokens }
}

function formatTokens(value) {
  return Number.isInteger(value) ? value.toLocaleString('zh-CN') : '—'
}

function formatTime(value) {
  if (!value) return '—'
  const time = new Date(value)
  return Number.isNaN(time.getTime()) ? value : time.toLocaleString('zh-CN', { hour12: false })
}

const resultTokens = computed(() => tokenTotals(result.value || {}))
const historyRows = computed(() => runHistory.value.map(run => {
  const details = run.details || {}
  return {
    ...run,
    ...tokenTotals(details),
    inserted: details.inserted || 0,
    updated: details.updated || 0,
    unchanged: details.unchanged || 0,
    error: details.error || '',
  }
}))

// 把新日志追加并自动滚到底部
async function pushLog(msg) {
  logLines.value.push(msg)
  await nextTick()
  if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
}

// 上传文件采集
function onPickAward(e) { fileForm.award_file = e.target.files[0] || null }
function onPickMeta(e) { fileForm.metadata_file = e.target.files[0] || null }

async function runFileCollect() {
  if (!form.conference_id) { ElMessage.warning('请先选择会议'); return }
  if (!fileForm.award_file) { ElMessage.warning('请先选择获奖页文件'); return }
  if (!llm.value.api_key) { ElMessage.warning('请先在“LLM 连接”中填写当前账户的 API Key'); return }
  running.value = true
  result.value = null
  logLines.value = []
  try {
    const fd = new FormData()
    fd.append('conference_id', form.conference_id)
    fd.append('year', form.year)
    fd.append('max_pages', form.max_pages)
    fd.append('award_file', fileForm.award_file)
    fd.append('award_url', fileForm.award_url)
    if (fileForm.metadata_file) {
      fd.append('metadata_file', fileForm.metadata_file)
      fd.append('metadata_url', fileForm.metadata_url)
    }
    fd.append('llm_provider', llm.value.provider)
    fd.append('llm_base_url', llm.value.base_url)
    fd.append('llm_model', llm.value.model)
    fd.append('llm_api_key', llm.value.api_key)
    result.value = await collectFilesStream(fd, pushLog)
    ElMessage.success(`采集完成：新增 ${result.value?.inserted || 0} 条`)
    await loadRuns()
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    running.value = false
  }
}

// 导入 JSON
async function onImportJson(e) {
  const file = e.target.files[0]
  if (!file) return
  try {
    const text = await file.text()
    const bundle = JSON.parse(text)
    const res = await api.importJson({ bundle })
    ElMessage.success(`导入完成：新增 ${res.inserted}，更新 ${res.updated}`)
    result.value = res
    await loadStats()
  } catch (err) {
    ElMessage.error(errMsg(err))
  } finally {
    e.target.value = ''
  }
}
</script>

<template>
  <div>
    <h2>采集与导入</h2>
    <p class="hint">自动搜索官网或使用已保存入口采集；新增记录默认待核验。真实采集会调用 API 并产生费用。</p>

    <el-row :gutter="16" v-if="stats" class="metrics">
      <el-col :span="8"><el-statistic title="已保存入口覆盖" :value="`${stats.conferences_with_seed}/${stats.total_conferences}`" /></el-col>
      <el-col :span="8"><el-statistic title="会议年度网址" :value="stats.seed_rows" /></el-col>
      <el-col :span="8"><el-statistic title="尚无入口" :value="stats.conferences_without_seed" /></el-col>
    </el-row>

    <el-card shadow="never" class="batch-card">
      <template #header><strong>查找获奖论文</strong></template>
      <p class="hint">会议和年份可任意多选；系统按“会议 × 年份”拆为每批最多 100 项、最多 20 个年份。每批结束后由你确认才继续，绝不自动启动下一批。每项独立记录结果和 Token 用量。</p>
      <el-form inline class="batch-form">
        <el-form-item label="会议（可多选）">
          <el-select v-model="batch.conference_ids" multiple filterable collapse-tags collapse-tags-tooltip :disabled="!!batchPlan"
            placeholder="输入会议简称并多选" style="width: 370px">
            <el-option v-for="c in conferences" :key="c.id" :label="conferenceLabel(c)" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="年份／区间">
          <el-input v-model="batch.years" :disabled="!!batchPlan" placeholder="例如 1990-2026, 2020" style="width: 245px" />
        </el-form-item>
        <el-form-item label="目标奖项">
          <el-checkbox-group v-model="batch.award_types" :disabled="!!batchPlan">
            <el-checkbox value="best_paper">最佳论文奖</el-checkbox>
            <el-checkbox value="best_student_paper">最佳学生论文奖</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="采集方式">
          <el-radio-group v-model="batch.strategy" :disabled="!!batchPlan">
            <el-radio value="auto">自动搜索官网</el-radio>
            <el-radio value="urls">使用各会议年度已保存网址</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="每项最多页面">
          <el-input-number v-model="batch.max_pages" :min="1" :max="20" :disabled="!!batchPlan" controls-position="right" style="width: 115px" />
        </el-form-item>
      </el-form>
      <div v-if="currentStrategy === 'urls' && currentChunk" class="seed-panel" v-loading="seedLoading">
        <div class="seed-head">
          <strong>本批已保存的会议年度网址（{{ currentChunk.count }} 项）</strong>
          <el-button size="small" @click="loadSelectedSeeds">刷新网址</el-button>
        </div>
        <p class="hint">只展示当前待执行批次；后续批次在切换到该批时展示。缺少网址可直接添加并保存，保存不会调用 LLM。</p>
        <el-alert v-if="seedError" type="error" :title="seedError" :closable="false" />
        <div v-for="target in savedSeeds" :key="seedKey(target.conference_id, target.year)" class="seed-target">
          <div class="seed-target-title">
            <strong>{{ conferences.find(c => c.id === target.conference_id)?.acronym || target.conference_id }} · {{ target.year }}</strong>
            <el-tag :type="target.urls.length ? 'success' : 'warning'" size="small">{{ target.urls.length ? `已保存 ${target.urls.length} 个网址` : '尚无网址' }}</el-tag>
          </div>
          <div v-if="target.urls.length" class="seed-links">
            <a v-for="url in target.urls" :key="url" :href="url" target="_blank" rel="noopener noreferrer">{{ url }}</a>
          </div>
          <el-input v-model="seedDrafts[seedKey(target.conference_id, target.year)]" type="textarea" :rows="2" placeholder="添加官网／获奖页网址，每行一个" />
          <el-button size="small" :loading="savingSeed === seedKey(target.conference_id, target.year)" :disabled="!!savingSeed" @click="saveTargetSeed(target)">保存网址</el-button>
        </div>
      </div>
      <el-alert v-if="batchUncertain" type="warning" :closable="false" show-icon title="上一批连接中断，服务器可能已完成部分任务。请先查看运行日志；重试本批可能重复计费。" />
      <div class="batch-actions">
        <span>共 {{ totalTaskCount }} 项、{{ totalBatchCount }} 批；每批单独确认</span>
        <span v-if="batchPlan">已执行 {{ nextBatchIndex }} / {{ totalBatchCount }} 批；成功 {{ planProgress.completed }}，失败 {{ planProgress.failed }}</span>
        <el-button v-if="!planFinished" type="primary" :loading="batchRunning" :disabled="running || seedLoading" @click="runBatch">{{ batchUncertain ? '核对后重试本批' : batchPlan ? '确认并继续下一批' : '确认并开始第一批' }}</el-button>
        <el-tag v-else type="success">全部批次已结束</el-tag>
        <el-button v-if="batchUncertain" @click="refreshPlanState">刷新计划状态与日志</el-button>
        <el-button v-if="batchPlan" :disabled="batchRunning" @click="resetBatchPlan">重新选择目标</el-button>
      </div>
      <el-table v-if="batchTasks.length" :data="batchTasks" size="small" stripe class="batch-results">
        <el-table-column prop="conference" label="会议" width="100" />
        <el-table-column prop="year" label="年份" width="75" />
        <el-table-column prop="status" label="状态" width="105" />
        <el-table-column prop="inserted" label="新增" width="70" />
        <el-table-column prop="updated" label="更新" width="70" />
        <el-table-column prop="unchanged" label="重复" width="70" />
        <el-table-column label="总 tokens" width="115"><template #default="scope">{{ formatTokens(tokenTotals(scope.row).totalTokens) }}</template></el-table-column>
        <el-table-column prop="error" label="说明" min-width="190" show-overflow-tooltip />
      </el-table>
      <p v-if="batchResult" class="hint">本批完成 {{ batchResult.completed }} / {{ batchResult.total }}，失败 {{ batchResult.failed }}；搜索 {{ formatTokens(batchTokenTotals.search) }} tokens，提取 {{ formatTokens(batchTokenTotals.extraction) }} tokens。</p>
      <div v-if="batchResult?.papers?.length" class="batch-papers">
        <div class="batch-paper-head"><strong>本批找到的论文（{{ batchResult.papers.length }}）</strong><el-button size="small" @click="exportBatchPapers">导出本批 CSV</el-button></div>
        <el-table :data="batchResult.papers" size="small" stripe max-height="340">
          <el-table-column prop="title" label="论文题目" min-width="280" />
          <el-table-column prop="acronym" label="会议" width="90" />
          <el-table-column prop="year" label="年份" width="75" />
          <el-table-column prop="award_name" label="奖项原名" min-width="190" />
          <el-table-column prop="status" label="状态" width="85" />
        </el-table>
      </div>
    </el-card>

    <el-divider>上传文件采集（网页打不开时用）</el-divider>
    <p class="hint">文件上传针对单个会议年度，独立于上方的网址采集任务。</p>
    <el-form inline class="bar">
      <el-form-item label="会议">
        <el-select
          v-model="form.conference_id"
          filterable
          clearable
          placeholder="输入会议简称或名称"
          :filter-method="filterConferences"
          style="width: 320px"
          @visible-change="onConferenceDropdown"
        >
          <el-option v-for="c in filteredConferences" :key="c.id" :label="conferenceLabel(c)" :value="c.id">
            <div class="conference-option">
              <strong>{{ c.acronym }}</strong>
              <el-tag :type="c.rank === 'A' ? 'danger' : 'warning'" size="small" effect="plain">CCF-{{ c.rank }}</el-tag>
              <span>{{ c.area }}</span>
            </div>
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item label="年份">
        <el-input-number v-model="form.year" :min="1900" :max="2200" controls-position="right" style="width: 120px" />
      </el-form-item>
      <el-form-item label="最多页面">
        <el-input-number v-model="form.max_pages" :min="1" :max="20" controls-position="right" style="width: 110px" />
      </el-form-item>
    </el-form>

    <el-form inline>
      <el-form-item label="获奖页文件">
        <input type="file" accept=".txt,.html,.htm,.pdf" @change="onPickAward" />
      </el-form-item>
      <el-form-item label="获奖来源 URL">
        <el-input v-model="fileForm.award_url" placeholder="https://…" style="width:240px" />
      </el-form-item>
      <el-form-item label="论文文件">
        <input type="file" accept=".txt,.html,.htm,.pdf" @change="onPickMeta" />
      </el-form-item>
      <el-form-item label="论文来源 URL">
        <el-input v-model="fileForm.metadata_url" placeholder="上传论文时必填" style="width:220px" />
      </el-form-item>
      <el-form-item>
        <el-button type="success" :loading="running" :disabled="batchRunning" @click="runFileCollect">上传并提取</el-button>
      </el-form-item>
    </el-form>
    <el-upload :show-file-list="false" :auto-upload="false" @change="onImportJson">
      <el-button>导入 JSON</el-button>
    </el-upload>

    <!-- 实时滚动日志 -->
    <el-card shadow="never" class="logcard">
      <template #header>
        <span>实时日志</span>
        <el-tag v-if="running || batchRunning" type="warning" size="small" style="margin-left:8px">采集中…</el-tag>
      </template>
      <div ref="logBox" class="logbox">
        <div v-for="(line, i) in logLines" :key="i" class="logline">{{ line }}</div>
        <div v-if="!logLines.length" class="empty">（暂无日志，点击“开始采集”或“上传并提取”）</div>
      </div>
    </el-card>

    <el-card v-if="result && result.inserted !== undefined" shadow="never" class="result">
      <template #header>本次结果</template>
      <el-descriptions :column="4" size="small" border>
        <el-descriptions-item label="新增">{{ result.inserted }}</el-descriptions-item>
        <el-descriptions-item label="更新">{{ result.updated }}</el-descriptions-item>
        <el-descriptions-item label="重复">{{ result.unchanged }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ result.status }}</el-descriptions-item>
        <el-descriptions-item label="搜索 tokens">{{ formatTokens(resultTokens.searchTokens) }}</el-descriptions-item>
        <el-descriptions-item label="搜索连接">{{ result.token_usage?.search?.provider || '—' }} / {{ result.token_usage?.search?.model || '—' }}</el-descriptions-item>
        <el-descriptions-item label="提取 tokens">{{ formatTokens(resultTokens.extractionTokens) }}</el-descriptions-item>
        <el-descriptions-item label="总 tokens">{{ formatTokens(resultTokens.totalTokens) }}</el-descriptions-item>
      </el-descriptions>
      <el-alert v-if="result.rejected?.length" type="warning" :title="`${result.rejected.length} 条未通过校验`" :closable="false" style="margin-top:8px" />
    </el-card>

    <el-card shadow="never" class="history">
      <template #header>
        <div class="history-head">
          <span>运行日志与 Token 用量 <small class="history-live">● 自动刷新（3 秒）</small></span>
          <div class="history-actions">
            <el-dropdown split-button size="small" :disabled="!historyTotal" @click="exportRuns('all')" @command="exportRuns">
              导出筛选范围 CSV
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="all">全部匹配记录</el-dropdown-item>
                  <el-dropdown-item command="recent">最近 50 条匹配记录</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button size="small" type="danger" plain :loading="deletingRuns" @click="deleteRunRange">按时间删除</el-button>
            <el-button size="small" :loading="historyLoading" @click="loadRuns()">刷新</el-button>
          </div>
        </div>
      </template>
      <div class="history-filters">
        <span>开始时间</span>
        <el-date-picker v-model="historyDates" type="datetimerange" value-format="x" start-placeholder="起始日期时间" end-placeholder="结束日期时间" range-separator="至" style="width:370px" />
        <el-select v-model="historyConference" clearable filterable placeholder="全部会议" style="width:180px">
          <el-option v-for="conference in conferences" :key="conference.id" :label="conferenceLabel(conference)" :value="conference.id" />
        </el-select>
        <el-select v-model="historyStatus" clearable placeholder="全部状态" style="width:145px">
          <el-option v-for="status in ['running', 'extracted', 'partial', 'no_results', 'failed']" :key="status" :label="status" :value="status" />
        </el-select>
        <span class="hint">匹配 {{ historyTotal }} 条，表格显示最近 50 条；删除仅作用于当前筛选范围内已结束的日志。</span>
      </div>
      <el-alert v-if="historyError" type="error" :title="historyError" :closable="false" />
      <el-table v-else-if="historyRows.length" :data="historyRows" v-loading="historyLoading" size="small" stripe>
        <el-table-column prop="id" label="任务" width="72" />
        <el-table-column prop="acronym" label="会议" width="90" />
        <el-table-column prop="year" label="年份" width="72" />
        <el-table-column label="开始时间" min-width="170">
          <template #default="scope">{{ formatTime(scope.row.started_at) }}</template>
        </el-table-column>
        <el-table-column label="耗时（秒）" width="105">
          <template #default="scope">{{ scope.row.duration_seconds == null ? '运行中' : scope.row.duration_seconds.toFixed(1) }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90" />
        <el-table-column prop="inserted" label="新增" width="70" />
        <el-table-column prop="updated" label="更新" width="70" />
        <el-table-column prop="unchanged" label="重复" width="70" />
        <el-table-column label="搜索 tokens" min-width="110">
          <template #default="scope">{{ formatTokens(scope.row.searchTokens) }}</template>
        </el-table-column>
        <el-table-column label="搜索连接" min-width="170" show-overflow-tooltip>
          <template #default="scope">{{ scope.row.details?.token_usage?.search?.provider || '—' }} / {{ scope.row.details?.token_usage?.search?.model || '—' }}</template>
        </el-table-column>
        <el-table-column label="提取 tokens" min-width="110">
          <template #default="scope">{{ formatTokens(scope.row.extractionTokens) }}</template>
        </el-table-column>
        <el-table-column label="总 tokens" min-width="100">
          <template #default="scope">{{ formatTokens(scope.row.totalTokens) }}</template>
        </el-table-column>
        <el-table-column prop="error" label="说明" min-width="180" show-overflow-tooltip />
      </el-table>
      <el-empty v-else-if="!historyLoading" description="尚无采集运行日志" :image-size="72" />
    </el-card>
  </div>
</template>

<style scoped>
h2 { margin: 0; }
.hint { color: #8494a8; font-size: 13px; }
.history-live { margin-left: 8px; color: #31946b; font-weight: normal; font-size: 12px; }
.history-filters { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
.metrics { margin: 12px 0; }
.batch-card { margin: 18px 0 24px; }
.batch-form { margin-top: 18px; }
.batch-actions { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; color: #62748a; font-size: 13px; }
.batch-results { margin-top: 18px; }
.batch-papers { margin-top: 18px; }
.batch-paper-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.seed-panel { margin: 6px 0 18px; padding: 16px; max-height: 520px; overflow-y: auto; border: 1px solid #dce5ef; border-radius: 6px; background: #f8fafc; }
.seed-head, .seed-target-title { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.seed-panel .hint { margin: 8px 0 12px; }
.seed-target { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; padding: 12px 0; border-top: 1px solid #e4ebf2; }
.seed-target-title, .seed-target :deep(.el-textarea) { width: 100%; }
.seed-links { display: flex; flex-direction: column; gap: 4px; max-width: 100%; }
.seed-links a { color: #246398; overflow-wrap: anywhere; }
.bar { margin-bottom: 4px; }
.logcard { margin-top: 12px; }
.logbox {
  height: 240px; overflow-y: auto; background: #0f1b2d;
  color: #d6e2f5; font-family: Consolas, monospace; font-size: 12px;
  padding: 10px; border-radius: 6px;
}
.logline { line-height: 1.6; white-space: pre-wrap; word-break: break-all; }
.empty { color: #5a6b82; }
.result { margin-top: 12px; }
.history { margin-top: 12px; }
.history-head { display: flex; align-items: center; justify-content: space-between; }
.history-actions { display: flex; align-items: center; gap: 8px; }
.conference-option { display: flex; align-items: center; gap: 8px; }
.conference-option span:last-child { color: #66758a; }
</style>

