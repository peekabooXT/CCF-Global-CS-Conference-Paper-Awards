<script setup>
import { t, locale } from '../i18n.js'
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api.js'
import RecordDetail from '../components/RecordDetail.vue'
import PaperPageHeading from '../components/PaperPageHeading.vue'
import PaperPagination from '../components/PaperPagination.vue'
import { DEFAULT_PAGE_SIZE, pageSlice } from '../pagination.js'
import { scholarUrl, externalPaperUrl, sourceUrl } from '../paperLinks.js'
import { overviewCsv } from '../paperOverview.js'
import { alphabeticalConferences } from '../conferenceOptions.js'

const props = defineProps({ meta: { type: Object, required: true } })
const emptyDescription = '暂无匹配的已核验论文，可调整筛选条件或等待下一次数据发布。'

const conferences = computed(() => alphabeticalConferences(props.meta?.conferences || []))
const awardCategories = computed(() => props.meta?.award_categories || {})
const statusKeys = computed(() => Object.keys(props.meta?.statuses || {}))

const defaults = () => ({
  conference: null, rank: null, category: null,
  year_from: null, year_to: null,
  author: '', affiliation: '', title: '',
  status: 'verified', published_from: null, published_to: null,
})

const filters = reactive(defaults())
const page = ref(1)
const pageSize = ref(DEFAULT_PAGE_SIZE)
const pageRecords = computed(() => pageSlice(records.value, page.value, pageSize.value))
function resetFilters() { Object.assign(filters, defaults()); runSearch() }
const loading = ref(false)
const records = ref([])
const applied = ref(null)
const selectedId = ref(null)
const drawer = ref(false)

const conferenceLabel = (c) => c ? `${c.acronym} · ${c.rank} 类 · ${t(c.area)}` : '全部会议'

async function runSearch() {
  if (loading.value) return
  if (filters.year_from && filters.year_to && filters.year_from > filters.year_to) { ElMessage.warning(t('起始年份不能晚于结束年份')); return }
  if (filters.published_from && filters.published_to && filters.published_from > filters.published_to) { ElMessage.warning(t('发表起点不能晚于终点')); return }
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

function downloadCsv() {
  if (!applied.value) return
  const url = URL.createObjectURL(new Blob([overviewCsv(records.value, props.meta.statuses, locale.value)], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a'); link.href = url; link.download = `paper-search-${locale.value}.csv`; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
onMounted(runSearch)
</script>

<template>
  <div class="search-workspace">
    <PaperPageHeading class="search-page-heading" :title="t(&quot;获奖论文检索&quot;)" :description="t(&quot;按会议、奖项与年份查找计算机领域获奖论文，查看原始奖项名称和可核验来源。&quot;)" :meta="meta" />
    <aside class="filter-sidebar" :aria-label="t(&quot;检索设置&quot;)">
      <div class="sidebar-heading"><h2>{{ t("检索设置") }}</h2></div>
      <el-form :model="filters" label-position="top" class="filter-form" @submit.prevent="runSearch">
        <el-form-item :label="t(&quot;CCF 等级&quot;)">
          <el-select v-model="filters.rank" :placeholder="t(&quot;全部（CCF A / B）&quot;)" clearable>
            <el-option label="CCF A" value="A" />
            <el-option label="CCF B" value="B" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t(&quot;奖项分类&quot;)">
          <el-select v-model="filters.category" :placeholder="t(&quot;全部奖项分类&quot;)" clearable>
            <el-option v-for="(label, key) in awardCategories" :key="key" :label="t(label)" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t(&quot;会议名称&quot;)">
          <el-select v-model="filters.conference" :placeholder="t(&quot;输入会议简称查找&quot;)" filterable clearable>
            <el-option v-for="c in conferences" :key="c.id" :label="t(conferenceLabel(c))" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t(&quot;获奖年份&quot;)">
          <div class="year-fields">
            <el-input-number v-model="filters.year_from" :min="1900" :max="2200" :placeholder="t(&quot;起始&quot;)" controls-position="right" />
            <span aria-hidden="true">—</span>
            <el-input-number v-model="filters.year_to" :min="1900" :max="2200" :placeholder="t(&quot;结束&quot;)" controls-position="right" />
          </div>
        </el-form-item>
        <el-form-item :label="t(&quot;作者&quot;)"><el-input v-model="filters.author" :placeholder="t(&quot;输入作者姓名&quot;)" clearable /></el-form-item>
        <el-form-item :label="t(&quot;单位&quot;)"><el-input v-model="filters.affiliation" :placeholder="t(&quot;输入作者单位&quot;)" clearable /></el-form-item>
        <el-form-item :label="t(&quot;标题关键词&quot;)"><el-input v-model="filters.title" :placeholder="t(&quot;输入标题关键词&quot;)" clearable /></el-form-item>
        <el-form-item :label="t(&quot;核验状态&quot;)">
          <el-select v-model="filters.status">
            <el-option v-for="k in statusKeys" :key="k" :label="t(meta.statuses[k])" :value="k" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t(&quot;发表日期&quot;)">
          <div class="date-fields">
            <el-date-picker v-model="filters.published_from" type="date" :placeholder="t(&quot;起始日期&quot;)" value-format="YYYY-MM-DD" />
            <el-date-picker v-model="filters.published_to" type="date" :placeholder="t(&quot;结束日期&quot;)" value-format="YYYY-MM-DD" />
          </div>
        </el-form-item>
        <div class="filter-actions">
          <el-button type="primary" native-type="submit" :loading="loading">{{ t("检索论文") }}</el-button>
          <el-button :disabled="loading" @click="resetFilters">{{ t("重置条件") }}</el-button>
        </div>
      </el-form>
    </aside>

    <section class="results-content" :aria-label="t(&quot;论文检索结果&quot;)">
      <div class="results-heading">
        <div>
          <span class="results-count" role="status" aria-live="polite">{{ loading ? t('正在检索…') : t(`共检索到 ${records.length.toLocaleString()} 篇论文`) }}</span>
          <span v-if="records.length" class="page-count">{{ t("当前显示 ") }}{{ (page - 1) * pageSize + 1 }}–{{ Math.min(page * pageSize, records.length) }}{{ t(" 篇") }}</span>
        </div>
        <el-button :disabled="!applied || loading || !records.length" @click="downloadCsv">{{ t("导出当前结果 CSV") }}</el-button>
      </div>
      <div class="paper-list" v-loading="loading">
        <article v-for="record in pageRecords" :key="record.id" class="paper-card">
          <div class="paper-main">
            <div class="paper-badges">
              <span v-if="record.rank" class="rank-badge">★ CCF {{ record.rank }}{{ t(" 类会议") }}</span>
              <span class="category-badge">{{ t(record.category_label || t('其他获奖')) }}</span>
            </div>
            <h2><button class="title-button" @click="openDetail(record.id)">{{ record.title }}</button></h2>
            <p v-if="authorLine(record)" class="paper-authors">{{ authorLine(record) }}</p>
            <p v-else class="paper-authors missing">{{ t("作者信息尚未提供") }}</p>
            <div class="paper-meta">
              <div class="paper-facts">
                <span><strong>{{ record.acronym || t('会议未映射') }}</strong> · {{ record.year }}</span>
                <span>{{ t("发表日期 ") }}{{ record.publication_date || t('未知') }}</span>
              </div>
              <div class="paper-links">
                <a :href="scholarUrl(record)" target="_blank" rel="noopener noreferrer">Google Scholar ↗</a>
                <a v-if="externalPaperUrl(record)" :href="externalPaperUrl(record)" target="_blank" rel="noopener noreferrer">{{ t("外部论文 ↗") }}</a>
                <a v-if="sourceUrl(record)" :href="sourceUrl(record)" target="_blank" rel="noopener noreferrer">{{ t("来源 ↗") }}</a>
                <button @click="openDetail(record.id)">{{ t("查看详情 →") }}</button>
              </div>
            </div>
          </div>
          <div class="paper-award">
            <span class="award-caption">{{ t("奖项原名") }}</span>
            <strong>{{ record.award_name || t('来源未提供') }}</strong>
            <div class="paper-review">
              <span class="award-caption">{{ t("核验状态") }}</span>
              <span class="status-pill" :class="`status-${record.status}`">{{ t(meta.statuses[record.status] || record.status) }}</span>
            </div>
          </div>
        </article>
        <el-empty v-if="!loading && !records.length" :description="t(emptyDescription)" />
      </div>
      <PaperPagination v-model:page="page" v-model:page-size="pageSize" :total="records.length" :disabled="loading" />
      <p class="results-note">{{ t("“最佳论文奖”采用 JeffHuang 收录口径；学生论文奖单列，其他奖项保留原名并归入其他获奖。") }}</p>
    </section>

    <el-drawer v-model="drawer" size="min(760px, 100vw)" :title="t(&quot;论文详情&quot;)">
      <RecordDetail v-if="selected" :record="selected" :awards="meta.awards" />
    </el-drawer>
  </div>
</template>

<style scoped>
.search-workspace{display:grid;grid-template-columns:270px minmax(0,1fr);align-items:start;gap:0 32px}
.search-page-heading{grid-column:1/-1}
.filter-sidebar{background:#fff;border:1px solid #dce8f5;border-radius:8px;padding:20px;box-shadow:0 7px 22px rgba(27,65,111,.035)}
.sidebar-heading{margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid #e8eff7}.sidebar-heading h2{font-size:18px;margin:0;color:#173b66}
.filter-form{display:block}.filter-form :deep(.el-form-item){display:block;margin-bottom:15px}.filter-form :deep(.el-form-item__label){font-weight:650;color:#526b88;margin-bottom:6px;padding:0;line-height:1.3}.filter-form :deep(.el-form-item__content){display:block}.filter-form :deep(.el-select),.filter-form :deep(.el-input),.filter-form :deep(.el-date-editor){width:100%}.filter-form :deep(.el-input__wrapper),.filter-form :deep(.el-select__wrapper){min-height:38px;box-shadow:0 0 0 1px #dce7f3 inset;border-radius:6px}
.year-fields{display:flex;align-items:center;gap:6px}.year-fields :deep(.el-input-number){width:calc(50% - 10px)}.year-fields>span{color:#8191a6}.date-fields{display:grid;gap:8px}.filter-actions{display:grid;gap:9px;margin-top:20px}.filter-actions .el-button{margin:0;width:100%;height:38px;border-radius:6px}
.results-content{min-width:0}
.results-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:0 0 14px;min-height:38px}.results-count{color:#233e63;font-weight:680}.page-count{color:#70839b;font-size:13px;margin-left:12px}.results-heading .el-button{border-radius:8px}
.paper-list{min-height:180px}.paper-card{display:grid;grid-template-columns:minmax(0,1fr) 190px;gap:16px;background:#fff;border:1px solid #dce8f5;border-radius:8px;padding:12px 16px;margin-bottom:8px;box-shadow:0 3px 12px rgba(27,65,111,.035);transition:border-color .2s,box-shadow .2s}.paper-card:hover{border-color:#9dccf9;box-shadow:0 5px 16px rgba(27,99,177,.08)}.paper-card:first-child{border-color:#9cc9f5}
.paper-main{min-width:0;overflow-wrap:anywhere}.paper-badges{display:flex;align-items:center;flex-wrap:wrap;gap:6px}.paper-badges span{display:inline-flex;align-items:center;min-height:20px;padding:1px 7px;border-radius:4px;font-size:11px;font-weight:650}.rank-badge{color:#1475d0;background:#e4f2ff}.category-badge{color:#456a95;background:#edf4fc}.paper-main h2{font-size:16px;line-height:1.35;margin:5px 0 4px}.title-button{padding:0;background:none;border:0;text-align:left;color:#122f58;font-weight:750;cursor:pointer;line-height:inherit}.title-button:hover{color:#1475d0;text-decoration:underline}.paper-authors{font-size:12px;color:#6c7f98;margin:0 0 6px;line-height:1.45}.paper-authors.missing{color:#9baabd}.paper-meta{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:3px 16px}.paper-facts{display:flex;gap:4px 12px;flex-wrap:wrap;color:#536b88;font-size:12px}.paper-facts strong{color:#263f64}.paper-links{display:flex;gap:14px;flex-wrap:wrap;font-size:12px}.paper-links a,.paper-links button{display:inline-flex;align-items:center;min-height:24px;color:#1780df;text-decoration:none;background:none;border:0;padding:0;font-weight:600;cursor:pointer}.paper-links a:hover,.paper-links button:hover{text-decoration:underline}
.paper-award{min-width:0;align-self:stretch;border-left:1px solid #e6edf6;padding-left:14px;display:flex;flex-direction:column;align-items:flex-start;justify-content:center;gap:3px}.award-caption{font-size:11px;color:#8293aa;font-weight:700;letter-spacing:.03em}.paper-award strong{font-size:12px;color:#294567;line-height:1.4;overflow-wrap:anywhere}.paper-review{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-top:5px}.status-pill{display:inline-block;border-radius:100px;padding:2px 8px;background:#eaf1fa;color:#58718e;font-size:12px;font-weight:650}.status-verified{background:#e7f7ef;color:#16845b}.status-pending{background:#fff4dc;color:#a57118}.status-rejected{background:#feecec;color:#be4c4c}
.results-note{margin:18px 0 0;color:#8293aa;font-size:12px;line-height:1.6}
@media(max-width:1050px){.search-workspace{gap:20px;grid-template-columns:240px minmax(0,1fr)}.paper-card{grid-template-columns:1fr;gap:8px}.paper-award{border-left:0;border-top:1px solid #e6edf6;padding:8px 0 0;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:start;gap:4px 10px}.paper-review{margin-top:0}}
@media(max-width:760px){.search-workspace{display:block}.filter-sidebar{margin-bottom:24px}.search-intro h1{font-size:27px}.paper-card{padding:12px}.paper-award{grid-template-columns:auto minmax(0,1fr)}.paper-review{grid-column:1/-1}.page-count{display:block;margin:4px 0 0}.results-heading{align-items:flex-start}}
.search-workspace{row-gap:0}
</style>



