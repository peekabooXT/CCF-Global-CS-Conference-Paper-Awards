<script setup>
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, errMsg, collectStream, collectBatchStream, collectFilesStream } from '../api.js'

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
  strategy: 'auto',          // auto | urls
  urls: '',
  extra_urls: '',
  max_pages: 4,
})
const batch = reactive({
  conference_ids: [], years: String(today), strategy: 'urls', max_pages: 4,
  award_types: ['best_paper', 'best_student_paper'],
})
const batchRunning = ref(false)
const batchResult = ref(null)
const batchTasks = ref([])
function parseBatchYears(value) {
  const years = new Set()
  for (const part of String(value || '').split(/[,，;；\s]+/).filter(Boolean)) {
    const match = part.match(/^(\d{4})(?:[-–—~至](\d{4}))?$/)
    if (!match) throw new Error(`无法识别年份：${part}；示例：2022-2026, 2020`)
    const start = Number(match[1])
    const end = Number(match[2] || match[1])
    if (start < 1900 || end > 2200 || start > end) throw new Error(`年份区间不正确：${part}`)
    for (let year = start; year <= end; year++) years.add(year)
  }
  if (!years.size || years.size > 20) throw new Error('请选择 1–20 个年份')
  return [...years].sort((a, b) => b - a)
}
const batchTaskCount = computed(() => {
  try { return batch.conference_ids.length * parseBatchYears(batch.years).length }
  catch { return 0 }
})
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
  if (!batch.conference_ids.length) { ElMessage.warning('请至少选择一个会议'); return }
  if (!batch.award_types.length) { ElMessage.warning('请至少选择一种奖项'); return }
  let years
  try { years = parseBatchYears(batch.years) }
  catch (e) { ElMessage.warning(e.message); return }
  const count = batch.conference_ids.length * years.length
  if (count > 100) { ElMessage.warning('一次最多执行 100 个会议×年份任务'); return }
  if (batch.strategy === 'auto' && llm.value.provider === 'deepseek' &&
      (llm.value.base_url || 'https://api.deepseek.com').includes('api.deepseek.com')) {
    ElMessage.warning('DeepSeek 官方 API 当前不支持 web_search；请使用已保存网址或更换 LLM 连接')
    return
  }
  try {
    await ElMessageBox.confirm(`将依次执行 ${count} 个独立采集任务，可能产生 API 费用。失败任务不会中断其余任务。确定开始吗？`,
      '确认批量采集', { type: 'warning', confirmButtonText: '开始采集', cancelButtonText: '取消' })
  } catch { return }
  batchRunning.value = true
  batchResult.value = null
  batchTasks.value = []
  logLines.value = []
  try {
    batchResult.value = await collectBatchStream({ ...batch, llm: { ...llm.value } }, pushLog, updateBatchTask)
    ElMessage.success(`批量采集结束：完成 ${batchResult.value.completed}，失败 ${batchResult.value.failed}`)
    await loadRuns()
  } catch (e) { ElMessage.error(errMsg(e)) }
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

// 文件上传
const fileForm = reactive({ award_file: null, award_url: '', metadata_file: null, metadata_url: '' })

async function loadStats() {
  try { stats.value = await api.seedStats() } catch (e) { /* 忽略 */ }
}

async function loadRuns() {
  historyLoading.value = true
  historyError.value = ''
  try {
    const res = await api.runs(50)
    runHistory.value = res.runs || []
  } catch (e) {
    historyError.value = errMsg(e)
  } finally {
    historyLoading.value = false
  }
}

function exportRuns() {
  const link = document.createElement('a')
  link.href = api.runExportUrl(500)
  link.download = ''
  document.body.appendChild(link)
  link.click()
  link.remove()
}

onMounted(() => {
  loadStats()
  loadRuns()
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

async function loadSeeds() {
  if (!form.conference_id) return
  try {
    const res = await api.seeds(form.conference_id, form.year)
    form.urls = res.urls.join('\n')
  } catch (e) { ElMessage.error(errMsg(e)) }
}

// 把新日志追加并自动滚到底部
async function pushLog(msg) {
  logLines.value.push(msg)
  await nextTick()
  if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
}

function baseBody() {
  return {
    conference_id: form.conference_id,
    year: form.year,
    strategy: form.strategy,
    urls: form.urls.split('\n').map(s => s.trim()).filter(Boolean),
    extra_urls: form.extra_urls.split('\n').map(s => s.trim()).filter(Boolean),
    max_pages: form.max_pages,
    llm: { ...llm.value },
  }
}

async function runCollect() {
  if (!form.conference_id) { ElMessage.warning('请先选择会议'); return }
  running.value = true
  result.value = null
  logLines.value = []
  try {
    result.value = await collectStream(baseBody(), pushLog)
    ElMessage.success(`采集完成：新增 ${result.value?.inserted || 0} 条`)
    await loadRuns()
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    running.value = false
  }
}

async function saveSeeds() {
  const urls = form.urls.split('\n').map(s => s.trim()).filter(Boolean)
  try {
    for (const url of urls) await api.addSeed({ conference_id: form.conference_id, year: form.year, url })
    ElMessage.success('年度入口已保存')
    await loadStats()
  } catch (e) { ElMessage.error(errMsg(e)) }
}

// 上传文件采集
function onPickAward(e) { fileForm.award_file = e.target.files[0] || null }
function onPickMeta(e) { fileForm.metadata_file = e.target.files[0] || null }

async function runFileCollect() {
  if (!form.conference_id) { ElMessage.warning('请先选择会议'); return }
  if (!fileForm.award_file) { ElMessage.warning('请先选择获奖页文件'); return }
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
      <template #header><strong>批量查找获奖论文</strong></template>
      <p class="hint">选择多个会议与年份，系统按“会议 × 年份”逐项采集；每项独立记录结果和 Token 用量。新增论文仍需按项目流程核验。</p>
      <el-form inline class="batch-form">
        <el-form-item label="会议（可多选）">
          <el-select v-model="batch.conference_ids" multiple filterable collapse-tags collapse-tags-tooltip
            placeholder="输入会议简称并多选" style="width: 370px">
            <el-option v-for="c in conferences" :key="c.id" :label="conferenceLabel(c)" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="年份／区间">
          <el-input v-model="batch.years" placeholder="例如 2022-2026, 2020" style="width: 245px" />
        </el-form-item>
        <el-form-item label="目标奖项">
          <el-checkbox-group v-model="batch.award_types">
            <el-checkbox value="best_paper">最佳论文奖</el-checkbox>
            <el-checkbox value="best_student_paper">最佳学生论文奖</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="采集方式">
          <el-radio-group v-model="batch.strategy">
            <el-radio value="auto">自动搜索官网</el-radio>
            <el-radio value="urls">使用各会议年度已保存网址</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="每项最多页面">
          <el-input-number v-model="batch.max_pages" :min="1" :max="20" controls-position="right" style="width: 115px" />
        </el-form-item>
      </el-form>
      <div class="batch-actions">
        <span>预计 {{ batchTaskCount }} 个独立任务（单次上限 100）</span>
        <el-button type="primary" :loading="batchRunning" :disabled="running" @click="runBatch">开始批量采集</el-button>
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
      <p v-if="batchResult" class="hint">完成 {{ batchResult.completed }} / {{ batchResult.total }}，失败 {{ batchResult.failed }}；搜索 {{ formatTokens(batchTokenTotals.search) }} tokens，提取 {{ formatTokens(batchTokenTotals.extraction) }} tokens。</p>
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

    <el-divider>单个会议／年份采集与手动导入</el-divider>

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
          @change="loadSeeds"
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
        <el-input-number v-model="form.year" :min="1900" :max="2200" controls-position="right" style="width: 120px" @change="loadSeeds" />
      </el-form-item>
      <el-form-item label="采集方式">
        <el-radio-group v-model="form.strategy">
          <el-radio value="auto">自动搜索官网</el-radio>
          <el-radio value="urls">使用已填网址</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="最多页面">
        <el-input-number v-model="form.max_pages" :min="1" :max="20" controls-position="right" style="width: 110px" />
      </el-form-item>
    </el-form>

    <el-form-item label="官网/获奖页" class="block">
      <el-input v-model="form.urls" type="textarea" :rows="3" placeholder="每行一个网址；切到该会议年份时会自动带出已保存入口" />
    </el-form-item>
    <el-form-item label="论文详情页" class="block">
      <el-input v-model="form.extra_urls" type="textarea" :rows="2" placeholder="可选，补全作者单位和发表日期" />
    </el-form-item>

    <div class="actions">
      <el-button type="primary" :loading="running" :disabled="batchRunning" @click="runCollect">开始采集</el-button>
      <el-button @click="saveSeeds">仅保存入口</el-button>
      <el-upload :show-file-list="false" :auto-upload="false" @change="onImportJson">
        <el-button>导入 JSON</el-button>
      </el-upload>
    </div>

    <el-divider>上传文件采集（网页打不开时用）</el-divider>
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
        <el-descriptions-item label="提取 tokens">{{ formatTokens(resultTokens.extractionTokens) }}</el-descriptions-item>
        <el-descriptions-item label="总 tokens">{{ formatTokens(resultTokens.totalTokens) }}</el-descriptions-item>
      </el-descriptions>
      <el-alert v-if="result.rejected?.length" type="warning" :title="`${result.rejected.length} 条未通过校验`" :closable="false" style="margin-top:8px" />
    </el-card>

    <el-card shadow="never" class="history">
      <template #header>
        <div class="history-head">
          <span>最近运行日志与 Token 用量</span>
          <div class="history-actions">
            <el-button size="small" :disabled="!historyRows.length" @click="exportRuns">导出 CSV</el-button>
            <el-button size="small" :loading="historyLoading" @click="loadRuns">刷新</el-button>
          </div>
        </div>
      </template>
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
.metrics { margin: 12px 0; }
.batch-card { margin: 18px 0 24px; }
.batch-form { margin-top: 18px; }
.batch-actions { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; color: #62748a; font-size: 13px; }
.batch-results { margin-top: 18px; }
.batch-papers { margin-top: 18px; }
.batch-paper-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.bar { margin-bottom: 4px; }
.block { display: flex; width: 100%; margin-bottom: 8px; }
.block :deep(.el-form-item__label) { width: 110px; }
.actions { margin: 12px 0; display: flex; gap: 8px; align-items: center; }
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

