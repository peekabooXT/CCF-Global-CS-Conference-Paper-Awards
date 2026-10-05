<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api.js'
import RecordDetail from '../components/RecordDetail.vue'

const props = defineProps({ meta: { type: Object, required: true } })

const conferences = computed(() => props.meta?.conferences || [])
const awardCategories = computed(() => props.meta?.award_categories || {})
const statusKeys = computed(() => Object.keys(props.meta?.statuses || {}))

const defaults = () => ({
  conference: null, rank: null, category: null,
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
const authorLine = (record) => record.authors?.length
  ? record.authors.map(author => author.name).filter(Boolean).join('、')
  : record.authors_raw || ''
const primarySource = (record) => record.paper_url || record.sources?.find(source => source.url)?.url || ''

function downloadCsv() {
  if (applied.value) window.open(api.exportUrl(applied.value), '_blank', 'noopener')
}
onMounted(runSearch)
</script>

<template>
  <div class="search-workspace">
    <aside class="filter-sidebar" aria-label="检索设置">
      <div class="sidebar-heading"><h2>检索设置</h2></div>
      <el-form :model="filters" label-position="top" class="filter-form" @submit.prevent="runSearch">
        <el-form-item label="CCF 等级">
          <el-select v-model="filters.rank" placeholder="全部（CCF A / B）" clearable>
            <el-option label="CCF A" value="A" />
            <el-option label="CCF B" value="B" />
          </el-select>
        </el-form-item>
        <el-form-item label="奖项分类">
          <el-select v-model="filters.category" placeholder="全部奖项分类" clearable>
            <el-option v-for="(label, key) in awardCategories" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="会议名称">
          <el-select v-model="filters.conference" placeholder="输入会议简称查找" filterable clearable>
            <el-option v-for="c in conferences" :key="c.id" :label="conferenceLabel(c)" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="获奖年份">
          <div class="year-fields">
            <el-input-number v-model="filters.year_from" :min="1900" :max="2200" placeholder="起始" controls-position="right" />
            <span aria-hidden="true">—</span>
            <el-input-number v-model="filters.year_to" :min="1900" :max="2200" placeholder="结束" controls-position="right" />
          </div>
        </el-form-item>
        <el-form-item label="作者"><el-input v-model="filters.author" placeholder="输入作者姓名" clearable /></el-form-item>
        <el-form-item label="单位"><el-input v-model="filters.affiliation" placeholder="输入作者单位" clearable /></el-form-item>
        <el-form-item label="标题关键词"><el-input v-model="filters.title" placeholder="输入标题关键词" clearable /></el-form-item>
        <el-form-item label="核验状态">
          <el-select v-model="filters.status">
            <el-option v-for="k in statusKeys" :key="k" :label="meta.statuses[k]" :value="k" />
          </el-select>
        </el-form-item>
        <el-form-item label="发表日期">
          <div class="date-fields">
            <el-date-picker v-model="filters.published_from" type="date" placeholder="起始日期" value-format="YYYY-MM-DD" />
            <el-date-picker v-model="filters.published_to" type="date" placeholder="结束日期" value-format="YYYY-MM-DD" />
          </div>
        </el-form-item>
        <div class="filter-actions">
          <el-button type="primary" native-type="submit" :loading="loading">检索论文</el-button>
          <el-button :disabled="loading" @click="resetFilters">重置条件</el-button>
        </div>
      </el-form>
    </aside>

    <section class="results-content" aria-label="论文检索结果">
      <div class="search-intro">
        <div class="eyebrow">GLOBAL CS PAPER AWARDS</div>
        <h1>获奖论文检索</h1>
        <p>按会议、奖项与年份查找计算机领域获奖论文，查看原始奖项名称和可核验来源。</p>
      </div>
      <div class="results-heading">
        <div>
          <span class="results-count" role="status" aria-live="polite">{{ loading ? '正在检索…' : `共检索到 ${records.length} 条论文` }}</span>
          <span v-if="records.length" class="page-count">当前显示 {{ (page - 1) * pageSize + 1 }}–{{ Math.min(page * pageSize, records.length) }} 条</span>
        </div>
        <el-button :disabled="!applied || loading || !records.length" @click="downloadCsv">导出当前结果 CSV</el-button>
      </div>
      <div class="paper-list" v-loading="loading">
        <article v-for="record in pageRecords" :key="record.id" class="paper-card">
          <div class="paper-main">
            <div class="paper-badges">
              <span v-if="record.rank" class="rank-badge">★ CCF {{ record.rank }} 类会议</span>
              <span class="category-badge">{{ record.category_label || '其他获奖' }}</span>
            </div>
            <h2><button class="title-button" @click="openDetail(record.id)">{{ record.title }}</button></h2>
            <p v-if="authorLine(record)" class="paper-authors">{{ authorLine(record) }}</p>
            <p v-else class="paper-authors missing">作者信息尚未提供</p>
            <div class="paper-facts">
              <span><strong>{{ record.acronym || '会议未映射' }}</strong> · {{ record.year }}</span>
              <span>发表日期 {{ record.publication_date || '未知' }}</span>
            </div>
            <div class="paper-links">
              <a v-if="primarySource(record)" :href="primarySource(record)" target="_blank" rel="noopener noreferrer">查看论文或来源 ↗</a>
              <button @click="openDetail(record.id)">查看详情 →</button>
            </div>
          </div>
          <div class="paper-award">
            <span class="award-caption">奖项原名</span>
            <strong>{{ record.award_name || '来源未提供' }}</strong>
            <span class="award-caption status-caption">核验状态</span>
            <span class="status-pill" :class="`status-${record.status}`">{{ meta.statuses[record.status] || record.status }}</span>
          </div>
        </article>
        <el-empty v-if="!loading && !records.length" description="暂无匹配论文；可调整筛选条件，或前往“采集与导入”开始收集。" />
      </div>
      <el-pagination v-if="records.length" v-model:current-page="page" :page-size="pageSize" :total="records.length" layout="total, prev, pager, next" :pager-count="5" :disabled="loading" class="result-pages" />
      <p class="results-note">“最佳论文奖”采用 JeffHuang 收录口径；学生论文奖单列，其他奖项保留原名并归入其他获奖。</p>
    </section>

    <el-drawer v-model="drawer" size="min(760px, 100vw)" title="论文详情">
      <RecordDetail v-if="selected" :record="selected" :awards="meta.awards" />
    </el-drawer>
  </div>
</template>

<style scoped>
.search-workspace{display:grid;grid-template-columns:270px minmax(0,1fr);align-items:start;gap:32px}
.filter-sidebar{background:#fff;border:1px solid #dce8f5;border-radius:8px;padding:20px;box-shadow:0 7px 22px rgba(27,65,111,.035)}
.sidebar-heading{margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid #e8eff7}.sidebar-heading h2{font-size:18px;margin:0;color:#173b66}
.filter-form{display:block}.filter-form :deep(.el-form-item){display:block;margin-bottom:15px}.filter-form :deep(.el-form-item__label){font-weight:650;color:#526b88;margin-bottom:6px;padding:0;line-height:1.3}.filter-form :deep(.el-form-item__content){display:block}.filter-form :deep(.el-select),.filter-form :deep(.el-input),.filter-form :deep(.el-date-editor){width:100%}.filter-form :deep(.el-input__wrapper),.filter-form :deep(.el-select__wrapper){min-height:38px;box-shadow:0 0 0 1px #dce7f3 inset;border-radius:6px}
.year-fields{display:flex;align-items:center;gap:6px}.year-fields :deep(.el-input-number){width:calc(50% - 10px)}.year-fields>span{color:#8191a6}.date-fields{display:grid;gap:8px}.filter-actions{display:grid;gap:9px;margin-top:20px}.filter-actions .el-button{margin:0;width:100%;height:38px;border-radius:6px}
.results-content{min-width:0}.search-intro{padding:7px 0 18px}.eyebrow{font-size:11px;font-weight:750;letter-spacing:.14em;color:#2780df}.search-intro h1{font-size:32px;line-height:1.2;letter-spacing:-.02em;color:#102f59;margin:8px 0 9px}.search-intro p{font-size:14px;color:#70839b;margin:0;line-height:1.6}
.results-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:4px 0 14px;padding-top:14px;border-top:1px solid #e7edf5}.results-count{color:#233e63;font-weight:680}.page-count{color:#70839b;font-size:13px;margin-left:12px}.results-heading .el-button{border-radius:8px}
.paper-list{min-height:180px}.paper-card{display:grid;grid-template-columns:minmax(0,1fr) 210px;gap:22px;background:#fff;border:1px solid #dce8f5;border-radius:12px;padding:21px 22px;margin-bottom:13px;box-shadow:0 7px 22px rgba(27,65,111,.045);transition:border-color .2s,box-shadow .2s}.paper-card:hover{border-color:#9dccf9;box-shadow:0 10px 28px rgba(27,99,177,.1)}.paper-card:first-child{border-color:#9cc9f5}
.paper-badges{display:flex;align-items:center;flex-wrap:wrap;gap:7px}.paper-badges span{display:inline-flex;align-items:center;min-height:24px;padding:3px 9px;border-radius:5px;font-size:12px;font-weight:650}.rank-badge{color:#1475d0;background:#e4f2ff}.category-badge{color:#456a95;background:#edf4fc}.paper-main h2{font-size:19px;line-height:1.4;margin:10px 0 7px}.title-button{padding:0;background:none;border:0;text-align:left;color:#122f58;font-weight:750;cursor:pointer;line-height:inherit}.title-button:hover{color:#1475d0;text-decoration:underline}.paper-authors{font-size:13px;color:#6c7f98;margin:0 0 13px;line-height:1.6}.paper-authors.missing{color:#9baabd}.paper-facts{display:flex;gap:8px 18px;flex-wrap:wrap;color:#536b88;font-size:13px}.paper-facts strong{color:#263f64}.paper-links{display:flex;gap:18px;flex-wrap:wrap;margin-top:14px;font-size:13px}.paper-links a,.paper-links button{color:#1780df;text-decoration:none;background:none;border:0;padding:0;font-weight:600;cursor:pointer}.paper-links a:hover,.paper-links button:hover{text-decoration:underline}
.paper-award{align-self:stretch;border-left:1px solid #e6edf6;padding-left:20px;display:flex;flex-direction:column;align-items:flex-start;justify-content:center;gap:5px}.award-caption{font-size:11px;color:#8293aa;font-weight:700;letter-spacing:.03em}.paper-award strong{font-size:13px;color:#294567;line-height:1.5;overflow-wrap:anywhere}.status-caption{margin-top:14px}.status-pill{display:inline-block;border-radius:100px;padding:4px 10px;background:#eaf1fa;color:#58718e;font-size:12px;font-weight:650}.status-verified{background:#e7f7ef;color:#16845b}.status-pending{background:#fff4dc;color:#a57118}.status-rejected{background:#feecec;color:#be4c4c}
.result-pages{margin-top:20px;justify-content:flex-end;flex-wrap:wrap}.results-note{margin:23px 0 0;color:#8293aa;font-size:12px;line-height:1.6}
@media(max-width:1050px){.search-workspace{gap:20px;grid-template-columns:240px minmax(0,1fr)}.paper-card{grid-template-columns:1fr}.paper-award{border-left:0;border-top:1px solid #e6edf6;padding:13px 0 0;display:grid;grid-template-columns:auto 1fr;gap:5px 12px}.status-caption{margin:0}}
@media(max-width:760px){.search-workspace{display:block}.filter-sidebar{margin-bottom:24px}.search-intro h1{font-size:27px}.paper-card{padding:17px}.page-count{display:block;margin:4px 0 0}.results-heading{align-items:flex-start}}
</style>



