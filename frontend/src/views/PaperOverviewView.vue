<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api, errMsg } from '../api.js'
import RecordDetail from '../components/RecordDetail.vue'
import { authorText, affiliationText, overviewRows, overviewStats, overviewCsv } from '../paperOverview.js'
import { scholarUrl, externalPaperUrl, sourceUrl } from '../paperLinks.js'

const props = defineProps({ meta: { type: Object, required: true } })
const isPublic = props.meta.mode === 'public'
const defaults = () => ({ conferences: [], rank: '', category: '', year_from: null, year_to: null, query: '', status: isPublic ? 'verified' : 'active' })
const filters = reactive(defaults())
const records = ref([]), loading = ref(false), loadError = ref('')
const sort = ref('conference'), page = ref(1), pageSize = ref(100), expanded = ref(false)
const selected = ref(null), drawer = ref(false)
const invalidYears = computed(() => filters.year_from != null && filters.year_to != null && filters.year_from > filters.year_to)
const rows = computed(() => invalidYears.value ? [] : overviewRows(records.value, filters, sort.value))
const stats = computed(() => overviewStats(rows.value))
const pageRows = computed(() => rows.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const conferenceOptions = computed(() => {
  const counts = new Map()
  for (const record of records.value) counts.set(record.acronym, (counts.get(record.acronym) || 0) + 1)
  return [...counts].sort(([a], [b]) => a.localeCompare(b, 'en')).map(([acronym, count]) => {
    const record = records.value.find(item => item.acronym === acronym)
    return { acronym, label: `${acronym}${record.rank ? ` · CCF-${record.rank}` : ' · 未映射'} · ${count} 条` }
  })
})
watch([filters, sort, pageSize], () => { page.value = 1 }, { deep: true })

async function load() {
  if (loading.value) return
  loading.value = true
  loadError.value = ''
  try {
    // Reuse the existing read-only search endpoint; local managers can inspect all statuses.
    const result = await api.search({ status: isPublic ? 'verified' : 'all' })
    records.value = result.records
    page.value = 1
    if (selected.value) selected.value = records.value.find(record => record.id === selected.value.id) || null
  } catch (error) { loadError.value = errMsg(error) }
  finally { loading.value = false }
}
function reset() { Object.assign(filters, defaults()); sort.value = 'conference' }
function openDetail(record) { selected.value = record; drawer.value = true }
function authorSummary(record) {
  if (!record.authors?.length) return record.authors_raw || '作者未提供'
  const names = record.authors.map(author => author.name).filter(Boolean)
  return names.slice(0, 2).join('、') + (names.length > 2 ? ` 等 ${names.length} 位` : '')
}
function rowClass({ row, rowIndex }) {
  return sort.value === 'conference' && rowIndex > 0 && pageRows.value[rowIndex - 1].acronym !== row.acronym ? 'conference-start' : ''
}
function downloadCsv() {
  const url = URL.createObjectURL(new Blob([overviewCsv(rows.value, props.meta.statuses)], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `paper-overview-${new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })}.csv`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
onMounted(load)
</script>

<template>
  <section class="overview-workspace" aria-label="论文总览">
    <header class="overview-heading">
      <div><div class="eyebrow">GLOBAL CS PAPER AWARDS</div><h1>论文总览</h1><p>用紧凑表格批量筛查获奖论文；默认按会议 A–Z、年份从新到旧排列。</p></div>
      <el-button :loading="loading" @click="load">刷新数据</el-button>
    </header>
    <el-form label-position="top" size="small" class="overview-filters" @submit.prevent>
      <el-form-item label="会议（可多选）" class="conference-filter">
        <el-select v-model="filters.conferences" multiple filterable collapse-tags collapse-tags-tooltip :max-collapse-tags="2" clearable placeholder="全部已收录会议 · 输入简称查找">
          <template #header><el-button text size="small" @click="filters.conferences = conferenceOptions.map(item => item.acronym)">全选会议</el-button><el-button text size="small" @click="filters.conferences = []">清空选择</el-button></template>
          <el-option v-for="item in conferenceOptions" :key="item.acronym" :value="item.acronym" :label="item.label" />
        </el-select>
      </el-form-item>
      <el-form-item label="CCF 等级"><el-select v-model="filters.rank" clearable placeholder="全部等级"><el-option label="CCF A" value="A" /><el-option label="CCF B" value="B" /></el-select></el-form-item>
      <el-form-item label="奖项分类"><el-select v-model="filters.category" clearable placeholder="全部分类"><el-option v-for="(label, key) in meta.award_categories" :key="key" :value="key" :label="label" /></el-select></el-form-item>
      <el-form-item label="获奖年份" class="year-filter"><div class="year-range"><el-input-number v-model="filters.year_from" placeholder="起始" :controls="false" /><span>—</span><el-input-number v-model="filters.year_to" placeholder="结束" :controls="false" /></div></el-form-item>
      <el-form-item label="快速筛查" class="query-filter"><el-input v-model="filters.query" clearable placeholder="题名、作者、单位、奖项 · 多个关键词用空格分隔" /></el-form-item>
      <el-form-item label="排列方式"><el-select v-model="sort"><el-option label="会议 A–Z / 年份倒序" value="conference" /><el-option label="年份从新到旧" value="year" /><el-option label="论文题名 A–Z" value="title" /></el-select></el-form-item>
      <el-form-item v-if="!isPublic" label="核验状态"><el-select v-model="filters.status"><el-option v-for="(label, key) in meta.statuses" :key="key" :value="key" :label="label" /></el-select></el-form-item>
      <div class="filter-reset"><el-button size="small" @click="reset">重置条件</el-button></div>
    </el-form>
    <p v-if="invalidYears" class="overview-error" role="alert">起始年份不能晚于结束年份，请调整年份范围。</p>
    <div v-if="loadError" class="overview-error" role="alert">数据加载失败：{{ loadError }}<el-button link type="primary" @click="load">重试</el-button></div>
    <div class="overview-toolbar">
      <div class="overview-summary" role="status" aria-live="polite"><strong>{{ stats.records.toLocaleString() }} 条记录</strong><span>{{ stats.papers.toLocaleString() }} 篇论文 · {{ stats.conferences }} 个会议<span v-if="stats.yearFrom != null"> · {{ stats.yearFrom }}–{{ stats.yearTo }}</span></span></div>
      <div class="overview-tools"><el-checkbox v-model="expanded" size="small">展开长文本</el-checkbox><el-select v-model="pageSize" size="small" aria-label="每页条数" class="page-size"><el-option v-for="size in [50, 100, 200, 500]" :key="size" :value="size" :label="`每页 ${size} 条`" /></el-select><el-button size="small" :disabled="loading || !!loadError || !rows.length" @click="downloadCsv">导出筛选结果 CSV</el-button></div>
    </div>
    <div class="overview-table-shell" :class="{ expanded }">
      <el-table :data="pageRows" row-key="id" v-loading="loading" size="small" border stripe height="min(68vh, 720px)" :row-class-name="rowClass" empty-text="暂无匹配论文，请调整筛选条件" class="overview-table">
        <el-table-column label="会议 / 年份" width="125" fixed="left"><template #default="{ row }"><strong class="table-conference">{{ row.acronym }}</strong><div class="table-muted">{{ row.year }}<span v-if="row.rank"> · CCF-{{ row.rank }}</span></div></template></el-table-column>
        <el-table-column label="论文题名" min-width="380"><template #default="{ row }"><a class="table-title clamped" :href="scholarUrl(row)" :title="`${row.title} · 在 Google Scholar 检索（外部网站）`" target="_blank" rel="noopener noreferrer">{{ row.title }}</a></template></el-table-column>
        <el-table-column label="作者 / 单位" min-width="240"><template #default="{ row }"><span class="clamped" :title="authorText(row)">{{ expanded ? authorText(row) || '作者未提供' : authorSummary(row) }}</span><span v-if="affiliationText(row)" class="table-muted clamped" :title="affiliationText(row)">{{ affiliationText(row) }}</span></template></el-table-column>
        <el-table-column label="分类 / 奖项原名" min-width="250"><template #default="{ row }"><span class="table-category">{{ meta.award_categories[row.category] || row.category_label || '其他获奖' }}</span><span class="table-muted clamped" :title="row.award_name || '来源未提供'">{{ row.award_name || '来源未提供' }}</span></template></el-table-column>
        <el-table-column label="状态" width="80"><template #default="{ row }"><span class="table-status" :class="`status-${row.status}`">{{ meta.statuses[row.status] || row.status }}</span></template></el-table-column>
        <el-table-column label="链接" width="90"><template #default="{ row }"><div class="table-links"><a v-if="externalPaperUrl(row)" :href="externalPaperUrl(row)" target="_blank" rel="noopener noreferrer">外部论文 ↗</a><a v-if="sourceUrl(row)" :href="sourceUrl(row)" target="_blank" rel="noopener noreferrer">来源 ↗</a><button @click="openDetail(row)">详情</button></div></template></el-table-column>
      </el-table>
    </div>
    <div class="overview-bottom"><p>点击题名跳转 Google Scholar；“详情”查看本站记录。本站仅提供外部链接，不托管或提供论文文件下载。导出仅包含筛选后的书目信息，不含论文附件。</p><el-pagination v-if="rows.length" v-model:current-page="page" :page-size="pageSize" :total="rows.length" :pager-count="5" size="small" layout="total, prev, pager, next" /></div>
    <el-drawer v-model="drawer" size="min(760px, 100vw)" title="论文详情"><RecordDetail v-if="selected" :record="selected" :awards="meta.awards" /></el-drawer>
  </section>
</template>

<style scoped>
.table-title{text-decoration:none}
.overview-workspace{min-width:0;background:#fff;border:1px solid #dce8f5;border-radius:10px;padding:22px 24px;box-shadow:0 5px 20px #1b416f06}.overview-heading{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:18px}.eyebrow{font-size:10px;font-weight:750;letter-spacing:.13em;color:#2780df}.overview-heading h1{font-size:26px;color:#102f59;margin:5px 0}.overview-heading p{font-size:13px;color:#70839b;margin:0}.overview-filters{display:grid;grid-template-columns:minmax(240px,2fr) minmax(110px,1fr) minmax(160px,1fr) minmax(210px,1.2fr);gap:10px 16px;padding:14px 16px;background:#f6f9fd;border:1px solid #e7eef7;border-radius:7px}.overview-filters :deep(.el-form-item){min-width:0;margin:0}.overview-filters :deep(.el-form-item__label){font-size:12px;padding:0;line-height:20px;margin-bottom:4px;color:#526b88}.overview-filters :deep(.el-select){width:100%}.query-filter{grid-column:span 2}.year-range{display:flex;gap:8px;align-items:center;min-width:0}.year-range :deep(.el-input-number){width:calc(50% - 13px);min-width:0}.year-range>span{color:#8191a6}.filter-reset{align-self:end}.overview-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:16px 0 10px}.overview-summary{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}.overview-summary strong{font-size:15px;color:#233e63}.overview-summary>span{font-size:12px;color:#70839b}.overview-tools{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.overview-tools .el-button{margin:0}.page-size{width:125px}.overview-table-shell{min-width:0;overflow:hidden;border-radius:6px}.overview-table{font-size:12px;min-height:320px;--el-table-header-bg-color:#eef4fc;--el-table-row-hover-bg-color:#edf6ff}.overview-table :deep(.el-table__cell){padding:5px 0;vertical-align:top}.overview-table :deep(.cell){padding:0 10px;line-height:1.45;word-break:normal;overflow-wrap:anywhere}.overview-table :deep(th.el-table__cell){padding:9px 0;font-weight:700;color:#526b88}.overview-table :deep(.conference-start td){border-top:2px solid #c5d9ee}.table-conference{color:#214872;font-size:12px}.table-muted{display:block;font-size:11px;color:#72839a;line-height:1.4;margin-top:2px}.table-title{background:none;border:0;padding:0;text-align:left;color:#126dc2;cursor:pointer;font-size:12px;font-weight:600;line-height:1.45}.table-title:hover{text-decoration:underline}.clamped{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}.table-category{font-size:11px;color:#365d8b}.table-status{font-size:11px;color:#62748a}.status-verified{color:#16845b}.status-pending{color:#a57118}.status-rejected{color:#be4c4c}.table-links{display:flex;gap:3px;flex-direction:column;align-items:flex-start}.table-links a,.table-links button{font-size:11px;color:#1476d4;text-decoration:none;background:none;border:0;padding:0;cursor:pointer;line-height:1.5}.table-links a:hover,.table-links button:hover{text-decoration:underline}.expanded .clamped{display:block;overflow:visible;-webkit-line-clamp:unset}.overview-error{font-size:13px;color:#b54a40;margin:10px 0}.overview-error .el-button{margin-left:8px}.overview-bottom{display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap;padding-top:12px}.overview-bottom p{font-size:11px;color:#8293aa;margin:0;max-width:700px}.overview-bottom :deep(.el-pagination){flex-wrap:wrap}button:focus-visible,a:focus-visible{outline:2px solid #90b8e6;outline-offset:2px}
@media(max-width:1050px){.overview-filters{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}.query-filter{grid-column:span 2}}
@media(max-width:600px){.overview-workspace{padding:16px 12px}.overview-heading{align-items:flex-start}.overview-heading h1{font-size:23px}.overview-heading p{font-size:12px}.overview-filters{grid-template-columns:minmax(0,1fr);padding:12px}.query-filter{grid-column:auto}.overview-summary{gap:5px}.overview-tools{gap:8px}.overview-bottom{gap:10px}}
</style>
