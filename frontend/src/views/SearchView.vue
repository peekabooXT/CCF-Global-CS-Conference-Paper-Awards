<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api.js'
import RecordDetail from '../components/RecordDetail.vue'

const props = defineProps({ meta: { type: Object, required: true } })

const conferences = computed(() => props.meta?.conferences || [])
const awardKeys = computed(() => Object.keys(props.meta?.awards || {}))
const statusKeys = computed(() => Object.keys(props.meta?.statuses || {}))

const defaults = () => ({
  conference: null, rank: null, award: null,
  year_from: null, year_to: null,
  author: '', affiliation: '', title: '',
  status: 'active', published_from: null, published_to: null,
})

const filters = reactive(defaults())
const page = ref(1)
const pageSize = 20
const pageRecords = computed(() => records.value.slice((page.value-1)*pageSize, page.value*pageSize))
function resetFilters() { Object.assign(filters, defaults()); runSearch() }
const loading = ref(false)
const records = ref([])
const applied = ref(null)
const selectedId = ref(null)
const drawer = ref(false)

const conferenceLabel = (c) => c ? `${c.acronym} · ${c.rank} 类 · ${c.area}` : '全部会议'

async function runSearch() {
  if (loading.value) return
  if (filters.year_from && filters.year_to && filters.year_from > filters.year_to) { ElMessage.warning('起始年份不能晚于结束年份'); return }
  if (filters.published_from && filters.published_to && filters.published_from > filters.published_to) { ElMessage.warning('发表起点不能晚于终点'); return }
  loading.value = true
  try {
    const body = { ...filters }
    // 空串转 null，日期对象转字符串
    for (const k of ['author', 'affiliation', 'title']) {
      if (!body[k]) body[k] = null
    }
    if (body.published_from) body.published_from = toDate(body.published_from)
    if (body.published_to) body.published_to = toDate(body.published_to)
    const res = await api.search(body)
    records.value = res.records
    applied.value = body
    page.value = 1

  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    loading.value = false
  }
}

function toDate(d) {
  if (!d) return null
  const date = d instanceof Date ? d : new Date(d)
  return date.toISOString().slice(0, 10)
}

function openDetail(id) {
  selectedId.value = id
  drawer.value = true
}

const selected = computed(() => records.value.find(r => r.id === selectedId.value))

function downloadCsv() {
  if (applied.value) window.open(api.exportUrl(applied.value), '_blank', 'noopener')
}
onMounted(runSearch)
</script>

<template>
  <div class="search-workspace">
    <h2>论文检索</h2>
    <p class="hint">组合筛选获奖论文，查看作者、发表时间和单位。</p>

    <el-form :model="filters" inline class="filter-form" @submit.prevent="runSearch">
      <el-form-item label="会议">
        <el-select v-model="filters.conference" placeholder="输入会议简称查找" filterable clearable style="width: 240px">
          <el-option v-for="c in conferences" :key="c.id" :label="conferenceLabel(c)" :value="c.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="CCF 等级">
        <el-select v-model="filters.rank" placeholder="全部" clearable style="width: 110px">
          <el-option label="A 类" value="A" />
          <el-option label="B 类" value="B" />
        </el-select>
      </el-form-item>
      <el-form-item label="奖项">
        <el-select v-model="filters.award" placeholder="两种奖项" clearable style="width: 160px">
          <el-option v-for="k in awardKeys" :key="k" :label="meta.awards[k]" :value="k" />
        </el-select>
      </el-form-item>
      <el-form-item label="年份">
        <el-input-number v-model="filters.year_from" :min="1900" :max="2200" placeholder="起" controls-position="right" style="width: 120px" />
        <span> – </span>
        <el-input-number v-model="filters.year_to" :min="1900" :max="2200" placeholder="止" controls-position="right" style="width: 120px" />
      </el-form-item>
      <el-form-item label="作者">
        <el-input v-model="filters.author" placeholder="如 Julie" clearable style="width: 140px" />
      </el-form-item>
      <el-form-item label="单位">
        <el-input v-model="filters.affiliation" placeholder="如 Stanford" clearable style="width: 160px" />
      </el-form-item>
      <el-form-item label="标题关键词">
        <el-input v-model="filters.title" clearable style="width: 180px" />
      </el-form-item>
      <el-form-item label="核验状态">
        <el-select v-model="filters.status" style="width: 150px">
          <el-option v-for="k in statusKeys" :key="k" :label="meta.statuses[k]" :value="k" />
        </el-select>
      </el-form-item>
      <el-form-item label="发表日期">
        <el-date-picker v-model="filters.published_from" type="date" placeholder="发表日期起" value-format="YYYY-MM-DD" />
        <span style="margin: 0 6px">–</span>
        <el-date-picker v-model="filters.published_to" type="date" placeholder="发表日期止" value-format="YYYY-MM-DD" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" native-type="submit" :loading="loading">搜索论文</el-button>
        <el-button :disabled="loading" @click="resetFilters">重置条件</el-button>
      </el-form-item>
    </el-form>

    <div class="results-heading"><span role="status" aria-live="polite">{{ loading ? '正在检索…' : `共 ${records.length} 条获奖记录` }}</span><el-button :disabled="!applied || loading || !records.length" @click="downloadCsv">导出当前结果 CSV</el-button></div>
    <el-table :data="pageRecords" empty-text="没有匹配记录，请减少筛选条件或更换关键词。" v-loading="loading" size="default" @row-dblclick="row => openDetail(row.id)">
      <el-table-column prop="title" label="论文名称" min-width="300" class-name="paper-title-cell" />
      <el-table-column prop="acronym" label="会议" width="100" />
      <el-table-column prop="rank" label="CCF" width="70" />
      <el-table-column prop="year" label="年份" width="80" />
      <el-table-column label="奖项" width="160">
        <template #default="{ row }">{{ meta.awards[row.award_type] }}</template>
      </el-table-column>
      <el-table-column label="发表日期" width="120">
        <template #default="{ row }">{{ row.publication_date || '未知' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">{{ meta.statuses[row.status] || row.status }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDetail(row.id)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination v-if="records.length" v-model:current-page="page" :page-size="pageSize" :total="records.length" layout="total, prev, pager, next" :pager-count="5" :disabled="loading" class="result-pages" />
    <p class="hint" v-if="records.length">双击行或点“详情”查看作者、单位和来源。</p>

    <el-drawer v-model="drawer" size="min(760px, 100vw)" title="论文详情">
      <RecordDetail v-if="selected" :record="selected" :awards="meta.awards" />
    </el-drawer>
  </div>
</template>

<style scoped>
h2 { margin: 0; }
.results-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:24px 0 14px;color:#45566c;font-size:14px}.result-pages{margin-top:20px;justify-content:flex-end;flex-wrap:wrap}:deep(.paper-title-cell .cell){white-space:normal;line-height:1.6;color:#174a7e}:deep(.el-table__row td){padding-top:12px;padding-bottom:12px}
.hint { color: #8494a8; font-size: 13px; }
.search-workspace { background: white; padding: 26px; border: 1px solid #dce4ee; border-radius: 8px; }
.filter-form { margin: 20px 0; padding: 20px 18px 0; background: #f5f8fc; border: 1px solid #dce4ee; border-radius: 6px; }
@media(max-width:650px){.search-workspace{padding:16px}.filter-form{padding:14px 10px 0;overflow-x:auto}}
</style>



