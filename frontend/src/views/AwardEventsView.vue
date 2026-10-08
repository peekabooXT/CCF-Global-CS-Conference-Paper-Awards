<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api.js'

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
    <h2>会议年度颁奖记录</h2>
    <p class="hint">按会议与年份查看颁发了哪些奖项，以及各奖项已收录的获奖论文数量。保留官网原始奖名与证据；完整颁奖数量以官方来源为准。</p>
    <el-form class="events-filters" @submit.prevent="load(true)">
      <el-form-item label="会议"><el-input v-model="filters.venue" clearable placeholder="例如 SIGIR" /></el-form-item>
      <el-form-item label="统一分类">
        <el-select v-model="filters.category" clearable placeholder="全部分类">
          <el-option v-for="(label, key) in props.meta.award_categories" :key="key" :label="label" :value="key" />
        </el-select>
      </el-form-item>
      <el-form-item label="奖项 / 论文"><el-input v-model="filters.query" clearable placeholder="输入关键词" /></el-form-item>
      <el-form-item class="events-filter-actions">
        <el-button class="events-search-button" type="primary" native-type="submit" :loading="loading">检索</el-button>
      </el-form-item>
    </el-form>
    <p class="hint">共 {{ result.total }} 条会议年度颁奖记录；“未映射”表示尚未可靠对应 CCF 会议目录。</p>
    <el-table :data="result.events" v-loading="loading" stripe style="width: 100%">
      <el-table-column prop="year" label="年份" width="80" />
      <el-table-column label="会议" width="150"><template #default="{ row }">{{ row.venue }}<span v-if="row.rank"> · CCF-{{ row.rank }}</span></template></el-table-column>
      <el-table-column prop="official_award_name" label="原始奖项名称" min-width="300" />
      <el-table-column prop="category_label" label="统一分类" width="150" />
      <el-table-column label="已收录获奖论文数" width="150"><template #default="{ row }">{{ row.paper_count }}</template></el-table-column>
      <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag :type="row.status === 'verified' ? 'success' : 'warning'" size="small">{{ row.status === 'verified' ? '已核验' : '待核验' }}</el-tag></template></el-table-column>
      <el-table-column label="操作" width="80"><template #default="{ row }"><el-button link type="primary" @click="openEvent(row.id)">查看</el-button></template></el-table-column>
    </el-table>
    <div class="pager"><el-pagination :current-page="page" :page-size="pageSize" :total="result.total" :disabled="loading" layout="prev, pager, next" @current-change="p => { offset = (p - 1) * pageSize; load() }" /></div>
    <el-drawer v-model="drawer" size="min(760px, 92vw)" :title="selected?.official_award_name || '会议年度颁奖详情'">
      <template v-if="selected">
        <p>{{ selected.venue }} · {{ selected.year }} · {{ selected.category_label }}<span v-if="selected.student_only"> · 学生奖</span></p>
        <p class="hint">原始奖名与统一分类并列展示；分类不替代原始称谓。事件和论文关联分别保留核验状态。</p>
        <el-divider />
        <article v-for="paper in selected.papers" :key="paper.annotation_id" class="paper">
          <h3>{{ paper.title }}</h3>
          <p>核验状态：{{ paper.status === 'verified' ? '已核验' : '待核验' }}</p>
          <p v-if="paper.authors_raw">作者（原文）：{{ paper.authors_raw }}</p>
          <p v-else>作者：待补全</p>
          <p v-if="paper.paper_url"><a :href="paper.paper_url" target="_blank" rel="noopener noreferrer">论文链接</a></p>
          <p><a :href="paper.source_url" target="_blank" rel="noopener noreferrer">奖项来源页</a> · {{ paper.annotation_id }}</p>
          <p v-if="paper.note" class="hint">标注疑点：{{ paper.note }}</p>
          <details v-if="paper.evidence.length"><summary>原文证据片段（{{ paper.evidence.length }}）</summary><ul><li v-for="(item, i) in paper.evidence" :key="i">{{ item.relation }}：{{ item.quote }}</li></ul></details>
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
