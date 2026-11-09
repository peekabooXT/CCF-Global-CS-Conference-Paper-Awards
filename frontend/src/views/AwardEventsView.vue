<script setup>
import { t } from '../i18n.js'
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api.js'
import { scholarUrl, externalPaperUrl, externalUrl } from '../paperLinks.js'

const props = defineProps({ meta: { type: Object, required: true } })
const filters = reactive({ venue: '', category: '', query: '' })
const result = ref({ total: 0, events: [] })
const selected = ref(null)
const drawer = ref(false)
const loading = ref(false)
const offset = ref(0)
const pageSize = 50
const page = computed(() => Math.floor(offset.value / pageSize) + 1)

async function load(reset = false) {
  if (loading.value) return
  if (reset) offset.value = 0
  loading.value = true
  try {
    result.value = await api.awardEvents({ ...filters, limit: pageSize, offset: offset.value })
  } catch (e) { ElMessage.error(errMsg(e)) }
  finally { loading.value = false }
}
async function openEvent(id) {
  try { selected.value = await api.awardEvent(id); drawer.value = true }
  catch (e) { ElMessage.error(errMsg(e)) }
}
onMounted(() => load())
</script>

<template>
  <div class="events-workspace">
    <h2>{{ t("会议年度奖项记录") }}</h2>
    <p class="hint">{{ t("按会议与年份查看颁发了哪些奖项，以及各奖项已收录的获奖论文数量。保留官网原始奖名与证据；完整颁奖数量以官方来源为准。") }}</p>
    <el-form class="events-filters" @submit.prevent="load(true)">
      <el-form-item :label="t(&quot;会议&quot;)"><el-input v-model="filters.venue" clearable :placeholder="t(&quot;例如 SIGIR&quot;)" /></el-form-item>
      <el-form-item :label="t(&quot;统一分类&quot;)">
        <el-select v-model="filters.category" clearable :placeholder="t(&quot;全部分类&quot;)">
          <el-option v-for="(label, key) in props.meta.award_categories" :key="key" :label="t(label)" :value="key" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t(&quot;奖项 / 论文&quot;)"><el-input v-model="filters.query" clearable :placeholder="t(&quot;输入关键词&quot;)" /></el-form-item>
      <el-form-item class="events-filter-actions">
        <el-button class="events-search-button" type="primary" native-type="submit" :loading="loading">{{ t("检索") }}</el-button>
      </el-form-item>
    </el-form>
    <p class="hint">{{ t("共 ") }}{{ result.total }}{{ t(" 条会议年度奖项记录；“未映射”表示尚未可靠对应 CCF 会议目录。") }}</p>
    <el-table :data="result.events" v-loading="loading" stripe style="width: 100%">
      <el-table-column prop="year" :label="t(&quot;年份&quot;)" width="80" />
      <el-table-column :label="t(&quot;会议&quot;)" width="150"><template #default="{ row }">{{ row.venue }}<span v-if="row.rank"> · CCF-{{ row.rank }}</span></template></el-table-column>
      <el-table-column prop="official_award_name" :label="t(&quot;原始奖项名称&quot;)" min-width="300" />
      <el-table-column  :label="t(&quot;统一分类&quot;)" width="170"><template #default="{ row }">{{ t(row.category_label) }}</template></el-table-column>
      <el-table-column :label="t(&quot;已收录获奖论文数&quot;)" width="150"><template #default="{ row }">{{ row.paper_count }}</template></el-table-column>
      <el-table-column :label="t(&quot;状态&quot;)" width="90"><template #default="{ row }"><el-tag :type="row.status === 'verified' ? 'success' : 'warning'" size="small">{{ row.status === 'verified' ? t('已核验') : t('待核验') }}</el-tag></template></el-table-column>
      <el-table-column :label="t(&quot;操作&quot;)" width="80"><template #default="{ row }"><el-button link type="primary" @click="openEvent(row.id)">{{ t("查看") }}</el-button></template></el-table-column>
    </el-table>
    <div class="pager"><el-pagination :current-page="page" :page-size="pageSize" :total="result.total" :disabled="loading" layout="prev, pager, next" @current-change="p => { offset = (p - 1) * pageSize; load() }" /></div>
    <el-drawer v-model="drawer" size="min(760px, 92vw)" :title="selected?.official_award_name || t('会议年度奖项详情')">
      <template v-if="selected">
        <p>{{ selected.venue }} · {{ selected.year }} · {{ t(selected.category_label) }}<span v-if="selected.student_only">{{ t(" · 学生奖") }}</span></p>
        <p class="hint">{{ t("原始奖名与统一分类并列展示；分类不替代原始称谓。事件和论文关联分别保留核验状态。") }}</p>
        <el-divider />
        <article v-for="paper in selected.papers" :key="paper.annotation_id" class="paper">
          <h3>{{ paper.title }}</h3>
          <p>{{ t("核验状态：") }}{{ paper.status === 'verified' ? t('已核验') : t('待核验') }}</p>
          <p v-if="paper.authors_raw">{{ t("作者（原文）：") }}{{ paper.authors_raw }}</p>
          <p v-else>{{ t("作者：待补全") }}</p>
          <p><a :href="scholarUrl(paper)" target="_blank" rel="noopener noreferrer">{{ t("Google Scholar 检索 ↗") }}</a><template v-if="externalPaperUrl(paper)"> · <a :href="externalPaperUrl(paper)" target="_blank" rel="noopener noreferrer">{{ t("外部论文 / 出版页面 ↗") }}</a></template></p>
          <p><a v-if="externalUrl(paper.source_url)" :href="externalUrl(paper.source_url)" target="_blank" rel="noopener noreferrer">{{ t("奖项来源页") }}</a> · {{ paper.annotation_id }}</p>
          <p v-if="paper.note" class="hint">{{ t("标注疑点：") }}{{ paper.note }}</p>
          <details v-if="paper.evidence.length"><summary>{{ t("原文证据片段（") }}{{ paper.evidence.length }}）</summary><ul><li v-for="(item, i) in paper.evidence" :key="i">{{ item.relation }}：{{ item.quote }}</li></ul></details>
        </article>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.events-workspace { background: #fff; border: 1px solid #dce5f1; border-radius: 7px; padding: 28px; }
.events-workspace h2 { margin-top: 0; color: #173b67; }
.hint { color: #61738c; line-height: 1.7; }
.events-filters { display: grid; grid-template-columns: minmax(0, 260px) minmax(0, 250px) minmax(0, 310px) 88px; align-items: start; gap: 12px 20px; }
.events-filters :deep(.el-form-item) { margin: 0; min-width: 0; }
.events-filters :deep(.el-form-item__label) { white-space: nowrap; }
.events-filters :deep(.el-form-item__content) { min-width: 0; }
.events-filters :deep(.el-select) { width: 100%; }
.events-search-button { width: 88px; height: 32px; margin: 0; }
.pager { display: flex; justify-content: flex-end; padding-top: 20px; }
.paper { border-bottom: 1px solid #e6ebf2; padding: 12px 0 20px; overflow-wrap: anywhere; }
.paper h3 { font-size: 16px; }
.paper a { color: #245b96; }
@media (max-width: 1050px) {
  .events-filters { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
}
@media (max-width: 600px) {
  .events-workspace { padding: 18px; }
  .events-filters { grid-template-columns: minmax(0, 1fr); }
}
</style>
