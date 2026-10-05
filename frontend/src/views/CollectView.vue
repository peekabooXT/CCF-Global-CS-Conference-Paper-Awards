<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { api, errMsg, collectBatchStream, collectFilesStream } from '../api.js'
import { planCollectionBatches } from '../collectionBatches.js'
import { JEFF_HUANG_VENUES, selectJeffHuangConferences } from '../jeffHuangConferences.js'

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
const allConferencesSelected = computed(() =>
  conferences.value.length > 0 && conferences.value.every(conference => batch.conference_ids.includes(conference.id)))
const jeffHuangSelection = computed(() => selectJeffHuangConferences(conferences.value))
const jeffHuangSelected = computed(() =>
  jeffHuangSelection.value.unmatched.length === 0 &&
  batch.conference_ids.length === JEFF_HUANG_VENUES.length &&
  jeffHuangSelection.value.ids.every(id => batch.conference_ids.includes(id)))
function selectJeffHuang() {
  if (batchPlan.value) return
  if (jeffHuangSelection.value.unmatched.length) {
    ElMessage.warning(`会议目录无法准确匹配：${jeffHuangSelection.value.unmatched.join('、')}`)
    return
  }
  batch.conference_ids = [...jeffHuangSelection.value.ids]
}
function selectAllConferences() {
  if (batchPlan.value) return
  batch.conference_ids = conferences.value.map(conference => conference.id)
}
function clearConferences() {
  if (batchPlan.value) return
  batch.conference_ids = []
}
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
const reviewDrafts = reactive({})
const autoReviews = ref([])
const REVIEWS_KEY = 'global-cs-awards-url-reviews'
const seedConfirmation = ref(null)
const seedConfirmationVisible = ref(false)
const seedLoading = ref(false)
const savingSeed = ref('')
const seedError = ref('')
let seedRequestId = 0
const seedKey = (cid, year) => `${cid}:${year}`
function restoreAutoReviews() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(REVIEWS_KEY) || '{}')
    if (Array.isArray(saved.items)) autoReviews.value = saved.items.filter(item =>
      item && typeof item.conference_id === 'string' && Number.isInteger(item.year) &&
      item.seed_review && Array.isArray(item.seed_review.saved_urls) &&
      Array.isArray(item.seed_review.candidate_urls))
    if (saved.drafts && typeof saved.drafts === 'object') Object.assign(reviewDrafts, saved.drafts)
  } catch { /* Session storage may be disabled or contain a stale value. */ }
}
function persistAutoReviews() {
  try { sessionStorage.setItem(REVIEWS_KEY, JSON.stringify({ items: autoReviews.value, drafts: { ...reviewDrafts } })) }
  catch { /* In-memory review remains available. */ }
}
watch(autoReviews, persistAutoReviews, { deep: true })
watch(reviewDrafts, persistAutoReviews, { deep: true })
async function loadSelectedSeeds() {
  const requestId = ++seedRequestId
  savedSeeds.value = []
  seedError.value = ''
  seedLoading.value = false
  const chunk = currentChunk.value
  if (!chunk) return
  seedLoading.value = true
  try {
    const res = await api.lookupSeeds(chunk.conference_ids, chunk.yearNumbers)
    if (requestId === seedRequestId) {
      savedSeeds.value = res.items || []
      for (const target of savedSeeds.value) {
        const key = seedKey(target.conference_id, target.year)
        if (!(key in seedDrafts)) seedDrafts[key] = target.urls.join('\n')
      }
    }
  } catch (e) {
    if (requestId === seedRequestId) seedError.value = errMsg(e)
  } finally {
    if (requestId === seedRequestId) seedLoading.value = false
  }
}
watch([currentStrategy, currentChunk], loadSelectedSeeds)

async function saveTargetSeed(target) {
  const key = seedKey(target.conference_id, target.year)
  openSeedConfirmation(target.conference_id, target.year, target.urls, seedDrafts[key])
}
function parseSeedDraft(text) {
  return [...new Set((text || '').split(/\r?\n/).map(url => url.trim()).filter(Boolean))]
}
function openSeedConfirmation(cid, year, saved, draft) {
  const urls = parseSeedDraft(draft)
  if (!urls.length) { ElMessage.warning('请填写至少一个核对过的官网／获奖页网址'); return }
  if (urls.length === saved.length && urls.every(url => saved.includes(url))) {
    ElMessage.info('网址未变化，无需重复保存')
    return
  }
  seedConfirmation.value = { conference_id: cid, year, expected_urls: [...saved], urls }
  seedConfirmationVisible.value = true
}
function useCandidate(cid, year, url) {
  const key = seedKey(cid, year)
  const current = parseSeedDraft(reviewDrafts[key])
  if (!current.includes(url)) current.push(url)
  reviewDrafts[key] = current.join('\n')
}
async function confirmSeedSave() {
  const proposal = seedConfirmation.value
  if (!proposal) return
  const key = seedKey(proposal.conference_id, proposal.year)
  savingSeed.value = key
  try {
    const res = await api.replaceSeeds({ ...proposal, confirmed: true })
    seedDrafts[key] = res.urls.join('\n')
    reviewDrafts[key] = res.urls.join('\n')
    for (const review of autoReviews.value) {
      if (seedKey(review.conference_id, review.year) === key) review.seed_review.saved_urls = [...res.urls]
    }
    seedConfirmationVisible.value = false
    seedConfirmation.value = null
    await loadSelectedSeeds()
    await loadStats()
    ElMessage.success(`${proposal.conference_id} ${proposal.year}：已保存 ${res.urls.length} 个核对后的网址`)
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
    if (plan.strategy === 'auto') {
      const finished = (batchResult.value.tasks || batchTasks.value).filter(task => task.seed_review)
      for (const task of finished) {
        const key = seedKey(task.conference_id, task.year)
        if (!(key in reviewDrafts)) reviewDrafts[key] = task.seed_review.saved_urls.join('\n') || task.seed_review.used_urls.join('\n')
      }
      const byTarget = new Map(autoReviews.value.map(task => [seedKey(task.conference_id, task.year), task]))
      for (const task of finished) byTarget.set(seedKey(task.conference_id, task.year), {
        conference_id: task.conference_id, conference: task.conference,
        year: task.year, seed_review: task.seed_review,
      })
      autoReviews.value = [...byTarget.values()]
    }
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
    link.download = 'global-cs-paper-awards-agent-batch.csv'
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
const showUpload = ref(false)
const showLiveLog = ref(false)
const showHistory = ref(false)
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
  if (showHistory.value && document.visibilityState === 'visible' && !historyLoading.value && !deletingRuns.value) loadRuns(true)
}

function toggleHistory() {
  showHistory.value = !showHistory.value
  if (showHistory.value) loadRuns()
}

onMounted(() => {
  restorePlanState()
  restoreAutoReviews()
  loadStats()
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
  if (!showLiveLog.value) return
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
      <el-col :span="8"><el-statistic title="已保存入口覆盖" :value="stats.conferences_with_seed"><template #suffix>/{{ stats.total_conferences }}</template></el-statistic></el-col>
      <el-col :span="8"><el-statistic title="会议年度网址" :value="stats.seed_rows" /></el-col>
      <el-col :span="8"><el-statistic title="尚无入口" :value="stats.conferences_without_seed" /></el-col>
    </el-row>

    <el-card shadow="never" class="batch-card">
      <template #header><strong>查找获奖论文</strong></template>
      <p class="hint">会议和年份可任意多选；系统按“会议 × 年份”拆为每批最多 100 项、最多 20 个年份。每批结束后由你确认才继续，绝不自动启动下一批。每项独立记录结果和 Token 用量。</p>
      <el-form inline class="batch-form">
        <el-form-item label="会议（可多选）">
          <div class="batch-conference-picker">
            <el-select v-model="batch.conference_ids" multiple filterable collapse-tags collapse-tags-tooltip :disabled="!!batchPlan"
              placeholder="输入会议简称并多选" class="batch-conference-select">
              <el-option v-for="c in conferences" :key="c.id" :label="conferenceLabel(c)" :value="c.id" />
            </el-select>
            <el-button size="small" :disabled="!!batchPlan || jeffHuangSelected || !conferences.length" @click="selectJeffHuang">选择 Jeff Huang 32 会</el-button>
            <el-button size="small" :disabled="!!batchPlan || allConferencesSelected || !conferences.length" @click="selectAllConferences">全选全部会议</el-button>
            <el-button size="small" :disabled="!!batchPlan || !batch.conference_ids.length" @click="clearConferences">清空</el-button>
            <span class="conference-selection-count">已选 {{ batch.conference_ids.length }} / {{ conferences.length }}</span>
          </div>
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
      <div v-if="currentChunk" class="seed-panel" v-loading="seedLoading">
        <div class="seed-head">
          <strong>本批已保存的会议年度网址（{{ currentChunk.count }} 项）</strong>
          <el-button size="small" @click="loadSelectedSeeds">刷新网址</el-button>
        </div>
        <p class="hint">{{ currentStrategy === 'auto' ? '自动搜索会优先尝试这些已保存入口，再搜索官网作对照。搜索候选不会自动覆盖网址；采集后请核对并确认。' : '只展示当前待执行批次；缺少网址请先填写并确认保存。保存网址不会调用 LLM。' }}</p>
        <el-alert v-if="seedError" type="error" :title="seedError" :closable="false" />
        <div v-for="target in savedSeeds" :key="seedKey(target.conference_id, target.year)" class="seed-target">
          <div class="seed-target-title">
            <strong>{{ conferences.find(c => c.id === target.conference_id)?.acronym || target.conference_id }} · {{ target.year }}</strong>
            <el-tag :type="target.urls.length ? 'success' : 'warning'" size="small">{{ target.urls.length ? `已保存 ${target.urls.length} 个网址` : '尚无网址' }}</el-tag>
          </div>
          <div v-if="target.urls.length" class="seed-links">
            <a v-for="url in target.urls" :key="url" :href="url" target="_blank" rel="noopener noreferrer">{{ url }}</a>
          </div>
          <el-input v-model="seedDrafts[seedKey(target.conference_id, target.year)]" type="textarea" :rows="2" placeholder="核对后的官网／获奖页网址，每行一个；可修改旧网址" />
          <el-button size="small" :loading="savingSeed === seedKey(target.conference_id, target.year)" :disabled="!!savingSeed" @click="saveTargetSeed(target)">核对并保存网址</el-button>
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
      <div v-if="autoReviews.length" class="review-panel">
        <div class="review-heading"><strong>官网网址核对（{{ autoReviews.length }} 项）</strong><span>搜索结果仅是候选；请打开页面核实会议、年份及奖项后再保存。</span></div>
        <div v-for="task in autoReviews" :key="seedKey(task.conference_id, task.year)" class="review-target">
          <div class="seed-target-title"><strong>{{ task.conference }} · {{ task.year }}</strong><el-tag :type="task.seed_review.search_error ? 'warning' : 'info'" size="small">{{ task.seed_review.search_error ? '搜索未完成' : '待人工核对' }}</el-tag></div>
          <p v-if="task.seed_review.search_error" class="review-warning">搜索核对失败：{{ task.seed_review.search_error }}；已保存网址仍优先尝试。</p>
          <div class="review-columns">
            <div><span class="review-label">原已保存网址</span><div v-if="task.seed_review.saved_urls.length" class="seed-links"><a v-for="url in task.seed_review.saved_urls" :key="url" :href="url" target="_blank" rel="noopener noreferrer">{{ url }}</a></div><span v-else class="hint">尚无已保存网址</span></div>
            <div><span class="review-label">本次搜索候选</span><div v-if="task.seed_review.candidate_urls.length" class="candidate-list"><div v-for="url in task.seed_review.candidate_urls" :key="url"><a :href="url" target="_blank" rel="noopener noreferrer">{{ url }}</a><el-button link type="primary" @click="useCandidate(task.conference_id, task.year, url)">加入待保存</el-button></div></div><span v-else class="hint">暂无候选</span></div>
          </div>
          <span class="review-label">核对后拟保存的网址（每行一个，可删除错误旧网址）</span>
          <el-input v-model="reviewDrafts[seedKey(task.conference_id, task.year)]" type="textarea" :rows="2" placeholder="请填写核对后的官网网址" />
          <el-button size="small" type="primary" plain :loading="savingSeed === seedKey(task.conference_id, task.year)" :disabled="!!savingSeed" @click="openSeedConfirmation(task.conference_id, task.year, task.seed_review.saved_urls, reviewDrafts[seedKey(task.conference_id, task.year)])">核对并保存到会议年度网址</el-button>
        </div>
      </div>
    </el-card>

    <el-dialog v-model="seedConfirmationVisible" title="确认修改会议年度网址" width="min(640px, calc(100vw - 24px))" class="seed-confirm-dialog" :close-on-click-modal="false">
      <template v-if="seedConfirmation">
        <p>请确认 <strong>{{ conferences.find(c => c.id === seedConfirmation.conference_id)?.acronym || seedConfirmation.conference_id }} · {{ seedConfirmation.year }}</strong> 的网址。保存后将以新列表替换该会议年度的旧列表，不影响其他会议或年份。</p>
        <div class="confirm-columns"><div><strong>当前已保存</strong><p v-for="url in seedConfirmation.expected_urls" :key="url">{{ url }}</p><p v-if="!seedConfirmation.expected_urls.length" class="hint">无</p></div><div><strong>确认后保存</strong><p v-for="url in seedConfirmation.urls" :key="url">{{ url }}</p></div></div>
        <el-alert type="warning" :closable="false" title="请先打开网址，核实页面确实对应所选会议、年份和奖项；搜索候选不等于已核实来源。" />
      </template>
      <template #footer><el-button @click="seedConfirmationVisible = false">取消</el-button><el-button type="primary" :loading="!!savingSeed" @click="confirmSeedSave">确认替换并保存</el-button></template>
    </el-dialog>

    <section class="upload-card" aria-labelledby="upload-title">
      <button class="upload-heading" type="button" :aria-expanded="showUpload" aria-controls="upload-content" @click="showUpload = !showUpload">
        <span class="upload-heading-copy"><span class="section-eyebrow">备用采集方式</span><span id="upload-title" class="upload-title" role="heading" aria-level="3">上传文件采集</span><span class="upload-description">网页无法直接读取时，上传单个会议年度的获奖页文件；论文文件可选。</span></span>
        <span class="upload-format">支持 PDF · HTML · TXT</span>
        <el-icon class="collapse-chevron" :class="{ open: showUpload }"><ArrowDown /></el-icon>
      </button>
      <div v-show="showUpload" id="upload-content">
        <el-form label-position="top" class="upload-form">
        <div class="upload-targets">
          <el-form-item label="会议">
            <el-select v-model="form.conference_id" filterable clearable placeholder="输入会议简称或名称" :filter-method="filterConferences" @visible-change="onConferenceDropdown">
              <el-option v-for="c in filteredConferences" :key="c.id" :label="conferenceLabel(c)" :value="c.id">
                <div class="conference-option"><strong>{{ c.acronym }}</strong><el-tag :type="c.rank === 'A' ? 'danger' : 'warning'" size="small" effect="plain">CCF-{{ c.rank }}</el-tag><span>{{ c.area }}</span></div>
              </el-option>
            </el-select>
          </el-form-item>
          <el-form-item label="年份"><el-input-number v-model="form.year" :min="1900" :max="2200" controls-position="right" /></el-form-item>
          <el-form-item label="最多页面"><el-input-number v-model="form.max_pages" :min="1" :max="20" controls-position="right" /></el-form-item>
        </div>
        <div class="upload-sources">
          <div class="upload-source">
            <div class="source-heading"><span class="source-number">01</span><div><strong>获奖页文件 <em>必填</em></strong><small>官方奖项页、公告或 PDF</small></div></div>
            <label class="file-picker"><input type="file" accept=".txt,.html,.htm,.pdf" @change="onPickAward" /><span class="picker-symbol">↑</span><span>{{ fileForm.award_file?.name || '点击选择获奖页文件' }}</span></label>
            <el-form-item label="获奖来源 URL"><el-input v-model="fileForm.award_url" placeholder="https://官方页面网址" /></el-form-item>
          </div>
          <div class="upload-source">
            <div class="source-heading"><span class="source-number">02</span><div><strong>论文文件 <em class="optional">可选</em></strong><small>用于补充作者、单位等元数据</small></div></div>
            <label class="file-picker"><input type="file" accept=".txt,.html,.htm,.pdf" @change="onPickMeta" /><span class="picker-symbol">↑</span><span>{{ fileForm.metadata_file?.name || '点击选择论文文件' }}</span></label>
            <el-form-item label="论文来源 URL"><el-input v-model="fileForm.metadata_url" placeholder="上传论文文件时必填" /></el-form-item>
          </div>
        </div>
        <div class="upload-actions"><el-button type="primary" :loading="running" :disabled="batchRunning" @click="runFileCollect">上传并提取</el-button><label class="json-picker"><input type="file" accept=".json,application/json" @change="onImportJson" />导入已有 JSON</label><span>上传文件仅用于本次任务，不替代会议年度已保存网址。</span></div>
        </el-form>
      </div>
    </section>

    <!-- 实时滚动日志 -->
    <el-card shadow="never" class="logcard" :body-style="showLiveLog ? {} : { padding: '0' }">
      <template #header>
        <button class="collapse-title" type="button" :aria-expanded="showLiveLog" aria-controls="live-log-content" @click="showLiveLog = !showLiveLog"><span>实时日志 <el-tag v-if="running || batchRunning" type="warning" size="small">采集中…</el-tag><small v-else-if="logLines.length">{{ logLines.length }} 条</small></span><el-icon class="collapse-chevron" :class="{open:showLiveLog}"><ArrowDown /></el-icon></button>
      </template>
      <div v-show="showLiveLog" id="live-log-content" ref="logBox" class="logbox">
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

    <el-card shadow="never" class="history" :body-style="showHistory ? {} : { padding: '0' }">
      <template #header>
        <button class="collapse-title" type="button" :aria-expanded="showHistory" aria-controls="history-content" @click="toggleHistory"><span>运行日志与 Token 用量 <small v-if="showHistory" class="history-live">● 自动刷新（3 秒）</small></span><el-icon class="collapse-chevron" :class="{open:showHistory}"><ArrowDown /></el-icon></button>
      </template>
      <div v-show="showHistory" id="history-content">
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
      </div>
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
.batch-conference-picker { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.batch-conference-select { width: 370px; max-width: 100%; }
.batch-conference-picker :deep(.el-button + .el-button) { margin-left: 0; }
.conference-selection-count { color: #7e91a8; font-size: 12px; white-space: nowrap; }
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
.review-panel{margin-top:22px;padding:20px;border:1px solid #bfdaf4;border-radius:12px;background:#f4f9ff}.review-heading{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;color:#163a64}.review-heading span{color:#70839b;font-size:12px}.review-target{background:white;border:1px solid #deebf7;border-radius:10px;padding:16px;margin-top:13px}.review-target .el-textarea{margin:8px 0 10px}.review-target .seed-target-title{margin-bottom:12px}.review-columns,.confirm-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:12px 0}.review-columns>div,.confirm-columns>div{min-width:0}.review-label{display:block;font-size:12px;font-weight:700;color:#627b99;margin-bottom:6px}.candidate-list>div{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:7px}.candidate-list a{min-width:0;overflow-wrap:anywhere;color:#1675c9;font-size:12px}.review-warning{color:#a36a19;font-size:12px;margin:6px 0}.confirm-columns>div{border:1px solid #e0e9f4;background:#f7faff;border-radius:8px;padding:12px}.confirm-columns p{font-size:12px;overflow-wrap:anywhere;margin:8px 0;color:#456487}
.upload-card{margin:24px 0 16px;padding:25px;background:#fff;border:1px solid #dce8f5;border-radius:12px;box-shadow:0 7px 22px rgba(27,65,111,.045)}.upload-heading{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;padding-bottom:18px;border-bottom:1px solid #e8eff7}.section-eyebrow{font-size:11px;font-weight:750;color:#2680d9;letter-spacing:.12em}.upload-heading h3{margin:6px 0 4px;color:#173b66;font-size:20px}.upload-heading p{margin:0;color:#70839b;font-size:13px}.upload-format{white-space:nowrap;background:#edf6ff;color:#3776b1;padding:7px 10px;border-radius:6px;font-size:12px;font-weight:650}.upload-targets{display:grid;grid-template-columns:minmax(240px,2fr) repeat(2,minmax(120px,1fr));gap:16px;margin-top:20px}.upload-targets :deep(.el-select),.upload-targets :deep(.el-input-number){width:100%}.upload-form :deep(.el-form-item__label){color:#526b88;font-weight:650}.upload-sources{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:4px}.upload-source{padding:18px;border:1px solid #e0ebf6;border-radius:10px;background:#f8fbff}.source-heading{display:flex;align-items:center;gap:10px;margin-bottom:15px}.source-heading strong{display:block;color:#23476e;font-size:14px}.source-heading small{display:block;color:#8294a9;margin-top:3px}.source-heading em{font-size:11px;font-style:normal;color:#1d7ccc;background:#e7f3ff;padding:2px 6px;border-radius:4px}.source-heading em.optional{color:#6b819a;background:#edf2f8}.source-number{color:#4093de;font-weight:800;font-size:18px}.file-picker{position:relative;min-height:74px;display:flex;align-items:center;justify-content:center;gap:10px;cursor:pointer;border:1px dashed #a9caec;border-radius:8px;background:white;color:#357bb5;font-size:13px;font-weight:650;overflow-wrap:anywhere;padding:10px;text-align:center}.file-picker:hover,.file-picker:focus-within{border-color:#1880dc;background:#f1f8ff}.picker-symbol{font-size:21px;line-height:1}.file-picker input,.json-picker input{position:absolute;width:1px;height:1px;opacity:0;overflow:hidden;clip-path:inset(50%)}.upload-source .el-form-item{margin:13px 0 0}.upload-source :deep(.el-input){width:100%}.upload-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:19px}.upload-actions>span{color:#8a9ab0;font-size:12px}.json-picker{position:relative;display:inline-flex;align-items:center;justify-content:center;border:1px solid #d6e4f2;border-radius:6px;padding:9px 14px;color:#446b91;cursor:pointer;font-size:13px;background:#fff}.json-picker:hover,.json-picker:focus-within{border-color:#1880dc;color:#1880dc}
.collapse-title{display:flex;align-items:center;justify-content:space-between;gap:12px;flex:1;min-width:0;padding:0;border:0;background:none;text-align:left;color:#183c63;font-size:16px;font-weight:650;cursor:pointer}.collapse-title small{margin-left:9px;color:#8494a8;font-size:12px;font-weight:400}.collapse-chevron{display:inline-block;color:#7a93ad;font-size:21px;transition:transform .2s}.collapse-chevron.open{transform:rotate(180deg)}.history-head{gap:16px}.history-actions{flex-wrap:wrap}.logcard,.history{border-radius:10px;border-color:#dce8f5}.logcard :deep(.el-card__header),.history :deep(.el-card__header){padding:16px 19px}
.upload-card { padding: 0; }
.upload-heading { display: grid; grid-template-columns: minmax(0, 1fr) auto 20px; width: 100%; align-items: center; gap: 18px; padding: 19px; border: 0; background: none; text-align: left; font: inherit; cursor: pointer; }
.upload-heading[aria-expanded="true"] { border-bottom: 1px solid #e8eff7; }
.upload-heading-copy { display: flex; flex-direction: column; min-width: 0; }
.upload-title { margin: 6px 0 4px; color: #173b66; font-size: 20px; font-weight: 700; }
.upload-description { color: #70839b; font-size: 13px; }
#upload-content { padding: 0 19px 19px; }
.collapse-title { width: 100%; }
.collapse-title > span:first-child { min-width: 0; }
.collapse-chevron { display: inline-flex; width: 20px; height: 20px; align-items: center; justify-content: center; flex: none; margin-left: auto; font-size: 18px; }
.upload-heading .collapse-chevron { margin-left: 0; }
.upload-heading:focus-visible, .collapse-title:focus-visible { outline: 2px solid #1675c9; outline-offset: -3px; }
.logcard :deep(.el-card__header), .history :deep(.el-card__header) { padding: 0; }
.logcard .collapse-title, .history .collapse-title { padding: 16px 19px; }
.history-actions { justify-content: flex-end; margin-bottom: 14px; }
@media(max-width:900px){.upload-targets{grid-template-columns:repeat(2,minmax(0,1fr))}.upload-targets .el-form-item:first-child{grid-column:1/-1}.upload-sources,.review-columns,.confirm-columns{grid-template-columns:1fr}.history-head{align-items:stretch;flex-direction:column}.history-actions{justify-content:flex-start}}
@media(max-width:600px){.batch-conference-select{width:100%}.upload-card{padding:16px}.upload-heading{flex-direction:column}.upload-targets{grid-template-columns:1fr;gap:0}.upload-targets .el-form-item:first-child{grid-column:auto}.upload-format{white-space:normal}.candidate-list>div{flex-direction:column;gap:2px}}
@media(max-width:600px){.upload-card{padding:0}.upload-heading{grid-template-columns:minmax(0,1fr) 20px;padding:16px 19px}.upload-heading .collapse-chevron{grid-column:2;grid-row:1 / span 2;align-self:center}.upload-format{grid-column:1;grid-row:2;justify-self:start}#upload-content{padding:0 16px 16px}}
</style>

