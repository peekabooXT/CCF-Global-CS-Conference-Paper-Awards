<script setup>
import { ref, reactive, computed, onMounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api.js'
import { parseBatchYears } from '../collectionBatches.js'

const props = defineProps({ meta: { type: Object, required: true } })
const conferences = computed(() => props.meta?.conferences || [])
const awardKeys = computed(() => Object.keys(props.meta?.awards || {}))
const stateKeys = computed(() => Object.keys(props.meta?.coverage || {}))
const today = new Date().getFullYear()
const query = reactive({ conference_ids: conferences.value.map(c => c.id), years: `${today - 2}-${today}` })
const allSelected = computed(() => conferences.value.length > 0 &&
  conferences.value.every(conference => query.conference_ids.includes(conference.id)))
const rows = ref([])
const summary = ref(null)
const totalRows = ref(0)
const page = ref(1)
const pageSize = 100
const loading = ref(false)
const error = ref('')
let requestId = 0

function selectAll() { query.conference_ids = conferences.value.map(c => c.id) }
function clearSelection() { query.conference_ids = [] }
function conferenceLabel(conference) {
  return `${conference.acronym} · CCF-${conference.rank} · ${conference.area}`
}
function rateText(rate) { return rate == null ? '—' : `${rate.toFixed(1)}%` }

const markForm = reactive({
  conference_id: null, year: today, award: null, state: 'partial', url: '', note: '', expected_count: '',
})
watch(() => markForm.state, (state, previous) => {
  if (state === 'not_offered') markForm.expected_count = '0'
  else if (previous === 'not_offered' && markForm.expected_count === '0') markForm.expected_count = ''
})

async function load(resetPage = true) {
  const currentRequest = ++requestId
  if (!query.conference_ids.length) {
    rows.value = []
    summary.value = null
    totalRows.value = 0
    loading.value = false
    error.value = '请至少选择一个会议'
    return
  }
  try { parseBatchYears(query.years) }
  catch (e) {
    rows.value = []
    summary.value = null
    totalRows.value = 0
    loading.value = false
    error.value = e.message
    return
  }
  if (resetPage) page.value = 1
  loading.value = true
  error.value = ''
  try {
    const res = await api.queryCoverage({
      conference_ids: [...query.conference_ids], years: query.years,
      offset: (page.value - 1) * pageSize, limit: pageSize,
    })
    if (currentRequest !== requestId) return
    rows.value = res.rows || []
    summary.value = res.summary || null
    totalRows.value = res.total_rows || 0
  } catch (e) {
    if (currentRequest === requestId) {
      rows.value = []
      summary.value = null
      totalRows.value = 0
      error.value = errMsg(e)
    }
  } finally {
    if (currentRequest === requestId) loading.value = false
  }
}

onMounted(() => load())

function changePage(value) {
  page.value = value
  load(false)
}

async function editRow(row) {
  markForm.conference_id = row.conference_id
  markForm.year = row.year
  markForm.award = row.award_type
  markForm.state = row.state
  markForm.url = row.evidence_url || ''
  markForm.note = row.note || ''
  markForm.expected_count = row.expected_count == null ? '' : String(row.expected_count)
  await nextTick()
  document.getElementById('coverage-mark-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function mark() {
  if (!markForm.conference_id || !markForm.award || !markForm.url.trim()) {
    ElMessage.warning('请填写会议、奖项及核对来源网址')
    return
  }
  const raw = markForm.expected_count.trim()
  if (markForm.state !== 'not_offered' && raw && (!/^[1-9]\d*$/.test(raw) || Number(raw) > 100000)) {
    ElMessage.warning('实际颁奖篇数应为正整数；尚未核实请留空')
    return
  }
  const expected_count = markForm.state === 'not_offered' ? 0 : (raw ? Number(raw) : null)
  try {
    await api.markCoverage({ ...markForm, expected_count })
    ElMessage.success('覆盖结论与实际颁奖篇数已保存')
    await load(false)
  } catch (e) { ElMessage.error(errMsg(e)) }
}
</script>

<template>
  <div>
    <h2>采集覆盖</h2>
    <p class="hint">按多个会议、多个年份和奖项检查。已找到篇数只统计待核验与已核验论文；实际颁奖篇数须依据官方名单登记，未知时不计算覆盖率。</p>

    <el-form inline class="coverage-filters">
      <el-form-item label="会议（可多选）">
        <div class="conference-picker">
          <el-select v-model="query.conference_ids" multiple filterable collapse-tags collapse-tags-tooltip
            placeholder="输入会议简称并多选" class="conference-select">
            <el-option v-for="c in conferences" :key="c.id" :label="conferenceLabel(c)" :value="c.id" />
          </el-select>
          <el-button size="small" :disabled="allSelected || !conferences.length" @click="selectAll">全选全部会议</el-button>
          <el-button size="small" :disabled="!query.conference_ids.length" @click="clearSelection">清空</el-button>
          <span class="selection-count">已选 {{ query.conference_ids.length }} / {{ conferences.length }}</span>
        </div>
      </el-form-item>
      <el-form-item label="年份／区间">
        <el-input v-model="query.years" placeholder="例如 2020-2026, 2018" style="width: 245px" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="loading" @click="load(true)">查看覆盖情况</el-button>
      </el-form-item>
    </el-form>
    <el-alert v-if="error" type="warning" :title="error" :closable="false" class="coverage-error" />

    <div v-if="summary" class="coverage-summary">
      <div class="summary-card"><span>已找到论文</span><strong>{{ summary.found_total }}</strong><small>所选会议、年份与两类奖项；不含已排除</small></div>
      <div class="summary-card"><span>已登记总数范围</span><strong>{{ summary.known_found }} / {{ summary.known_expected }}</strong><small>{{ summary.known_targets }} 项奖项已有实际颁奖篇数</small></div>
      <div class="summary-card accent"><span>已知范围覆盖率</span><strong>{{ rateText(summary.coverage_rate) }}</strong><small>按已找到篇数 ÷ 实际颁奖篇数计算</small></div>
      <div class="summary-card"><span>获奖总数待核对</span><strong>{{ summary.unknown_targets }} / {{ summary.targets }}</strong><small>未登记分母的项目不参与覆盖率</small></div>
    </div>
    <p v-if="summary" class="coverage-caveat">每一项代表“会议 × 年份 × 奖项”。{{ summary.unknown_targets ? '部分项目的实际颁奖篇数未知，上方百分比仅代表已登记总数的范围，不能当作全部所选目标的完整覆盖率。' : '全部所选项目的获奖总数已登记。' }}<span v-if="summary.over_expected_targets">另有 {{ summary.over_expected_targets }} 项找到篇数超过已登记总数，请复核。</span></p>

    <el-table :data="rows" v-loading="loading" border size="small" max-height="520">
      <el-table-column prop="acronym" label="会议" width="110" />
      <el-table-column prop="rank" label="CCF" width="70" />
      <el-table-column prop="year" label="年份" width="80" />
      <el-table-column label="奖项" width="160">
        <template #default="{ row }">{{ meta.awards[row.award_type] }}</template>
      </el-table-column>
      <el-table-column label="覆盖状态" width="120">
        <template #default="{ row }">{{ meta.coverage[row.state] }}</template>
      </el-table-column>
      <el-table-column label="待核验" width="90">
        <template #default="{ row }">{{ row.counts?.pending || 0 }}</template>
      </el-table-column>
      <el-table-column label="已核验" width="90">
        <template #default="{ row }">{{ row.counts?.verified || 0 }}</template>
      </el-table-column>
      <el-table-column label="已找到 / 实际颁奖" width="165">
        <template #default="{ row }"><span :class="{ 'over-count': row.expected_count != null && row.found_count > row.expected_count }">{{ row.found_count }} / {{ row.expected_count == null ? '待核对' : row.expected_count }}</span></template>
      </el-table-column>
      <el-table-column label="覆盖率" width="100">
        <template #default="{ row }"><span :class="{ 'over-count': row.coverage_rate > 100 }">{{ row.expected_count === 0 ? '未设奖' : rateText(row.coverage_rate) }}</span></template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ row }"><el-button link type="primary" @click="editRow(row)">登记总数</el-button></template>
      </el-table-column>
    </el-table>
    <div v-if="totalRows > pageSize" class="coverage-pagination"><span>共 {{ totalRows }} 项，当前每页 {{ pageSize }} 项</span><el-pagination :current-page="page" :page-size="pageSize" :total="totalRows" layout="prev, pager, next" @current-change="changePage" /></div>

    <el-divider>记录人工检查结论与获奖总数</el-divider>
    <p class="hint">请根据该会议该年度的官方奖项名单填写实际获奖论文篇数，并提供核对来源网址；未知时留空，不能用已找到篇数代替。</p>
    <el-form id="coverage-mark-form" :model="markForm" inline>
      <el-form-item label="会议">
        <el-select v-model="markForm.conference_id" style="width: 240px">
          <el-option v-for="c in conferences" :key="c.id" :label="conferenceLabel(c)" :value="c.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="年份">
        <el-input-number v-model="markForm.year" :min="1900" :max="2200" controls-position="right" style="width: 110px" />
      </el-form-item>
      <el-form-item label="奖项">
        <el-select v-model="markForm.award" style="width: 160px">
          <el-option v-for="k in awardKeys" :key="k" :label="meta.awards[k]" :value="k" />
        </el-select>
      </el-form-item>
      <el-form-item label="结论">
        <el-select v-model="markForm.state" style="width: 150px">
          <el-option v-for="k in stateKeys" :key="k" :label="meta.coverage[k]" :value="k" />
        </el-select>
      </el-form-item>
      <el-form-item label="该年实际颁奖篇数">
        <el-input v-model="markForm.expected_count" :disabled="markForm.state === 'not_offered'" inputmode="numeric" placeholder="未知请留空" style="width: 145px" />
      </el-form-item>
      <el-form-item label="来源网址">
        <el-input v-model="markForm.url" placeholder="官方奖项名单网址（必填）" style="width: 240px" />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="markForm.note" placeholder="检查备注" style="width: 240px" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="mark">保存覆盖结论与总数</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<style scoped>
h2 { margin: 0; }
.hint { color: #8494a8; font-size: 13px; }
.coverage-filters { margin-top: 18px; }
.conference-picker { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.conference-select { width: 370px; max-width: 100%; }
.conference-picker :deep(.el-button + .el-button) { margin-left: 0; }
.selection-count { color: #7e91a8; font-size: 12px; white-space: nowrap; }
.coverage-error { margin: 8px 0 14px; }
.coverage-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 16px 0 8px; }
.summary-card { display: flex; flex-direction: column; gap: 5px; min-width: 0; padding: 16px; border: 1px solid #dce8f5; border-radius: 10px; background: #f8fbff; }
.summary-card span { color: #647c99; font-size: 12px; }
.summary-card strong { color: #183d65; font-size: 23px; line-height: 1.2; }
.summary-card small { color: #8294aa; font-size: 11px; }
.summary-card.accent { border-color: #bcd7f4; background: #edf6ff; }
.summary-card.accent strong { color: #0f71c8; }
.coverage-caveat { margin: 0 0 15px; color: #7186a0; font-size: 12px; }
.coverage-caveat span, .over-count { color: #c45645; font-weight: 700; }
.coverage-pagination { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin: 14px 0; color: #7186a0; font-size: 12px; }
@media(max-width:1000px) { .coverage-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media(max-width:600px) { .conference-select { width: 100%; } .coverage-summary { grid-template-columns: 1fr; } .coverage-pagination { flex-direction: column; align-items: flex-start; } }
</style>
