<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api.js'

const filters = reactive({ venue: '', query: '', relation: '' })
const result = ref({ total: 0, listings: [] })
const selected = ref(null)
const drawer = ref(false)
const loading = ref(false)
const offset = ref(0)
const pageSize = 50
const page = computed(() => Math.floor(offset.value / pageSize) + 1)

async function load(reset = false) {
  if (reset) offset.value = 0
  loading.value = true
  try { result.value = await api.sourceListings({ ...filters, limit: pageSize, offset: offset.value }) }
  catch (e) { ElMessage.error(errMsg(e)) }
  finally { loading.value = false }
}
async function openListing(id) {
  try { selected.value = await api.sourceListing(id); drawer.value = true }
  catch (e) { ElMessage.error(errMsg(e)) }
}
function relationLabel(row) {
  if (row.event_count && row.record_count) return '关联事件与核验记录'
  if (row.event_count) return '关联获奖事件'
  if (row.record_count) return '关联核验记录'
  return '未关联现有记录'
}
onMounted(() => load())
</script>

<template>
  <div class="listings-workspace">
    <h2>来源收录</h2>
    <p class="hint">JeffHuang 汇总页收录的论文按会议、年份和题名去重。核验状态按记录显示；该表未逐条提供官方奖项名称，不会自动生成“最佳论文”获奖事件。</p>
    <el-form inline @submit.prevent="load(true)">
      <el-form-item label="会议"><el-input v-model="filters.venue" clearable placeholder="例如 AAAI" /></el-form-item>
      <el-form-item label="论文 / 作者"><el-input v-model="filters.query" clearable placeholder="输入关键词" /></el-form-item>
      <el-form-item label="去重关联">
        <el-select v-model="filters.relation" clearable placeholder="全部" style="width: 170px">
          <el-option label="关联获奖事件" value="event" />
          <el-option label="关联核验记录" value="record" />
          <el-option label="未关联现有记录" value="new" />
        </el-select>
      </el-form-item>
      <el-button type="primary" :loading="loading" @click="load(true)">检索</el-button>
    </el-form>
    <p class="hint">符合条件的收录：{{ result.total }} 条。与现有数据重合的论文只建立来源关联，不重复计为新的获奖事件。</p>
    <el-table :data="result.listings" v-loading="loading" stripe style="width: 100%">
      <el-table-column prop="year" label="年份" width="80" />
      <el-table-column label="会议" width="150"><template #default="{ row }">{{ row.source_venue }}<span v-if="row.rank"> · CCF-{{ row.rank }}</span></template></el-table-column>
      <el-table-column prop="title" label="论文题目" min-width="330" />
      <el-table-column label="去重结果" width="165"><template #default="{ row }">{{ relationLabel(row) }}</template></el-table-column>
      <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag size="small" :type="row.status === 'verified' ? 'success' : 'warning'">{{ row.status === 'verified' ? '已核验' : '待核验' }}</el-tag></template></el-table-column>
      <el-table-column label="操作" width="80"><template #default="{ row }"><el-button link type="primary" @click="openListing(row.id)">查看</el-button></template></el-table-column>
    </el-table>
    <div class="pager"><el-pagination :current-page="page" :page-size="pageSize" :total="result.total" layout="prev, pager, next" @current-change="p => { offset = (p - 1) * pageSize; load() }" /></div>
    <el-drawer v-model="drawer" size="min(760px, 92vw)" :title="selected?.title || '来源收录'">
      <template v-if="selected">
        <p>{{ selected.source_venue }} · {{ selected.year }} · JeffHuang 第 {{ selected.source_row }} 条</p>
        <p>收录核验状态：{{ selected.status === 'verified' ? '已核验' : '待核验' }}</p>
        <p v-if="selected.area_raw">网页领域：{{ selected.area_raw }}</p>
        <p v-if="selected.authors_raw">作者及单位（网页原文）：{{ selected.authors_raw }}</p>
        <p><a :href="selected.source_url" target="_blank" rel="noopener noreferrer">JeffHuang 汇总页</a></p>
        <p v-if="selected.discovery_url"><a :href="selected.discovery_url" target="_blank" rel="noopener noreferrer">Google Scholar 检索</a> <span class="hint">（不是论文正文或官方授奖证据）</span></p>
        <p v-if="selected.events.length">已关联获奖事件：<span v-for="(event, i) in selected.events" :key="event.id">{{ i ? '；' : '' }}{{ event.official_award_name }}（{{ event.status === 'verified' ? '已核验' : '待核验' }}）</span></p>
        <p v-if="selected.records.length">已关联现有论文记录：{{ selected.records.length }} 条</p>
        <p v-if="!selected.events.length && !selected.records.length" class="hint">尚未关联本项目的获奖事件或论文记录；这不影响本条收录的核验状态。</p>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.listings-workspace { background: #fff; border: 1px solid #dce5f1; border-radius: 7px; padding: 28px; }
.listings-workspace h2 { margin-top: 0; color: #173b67; }
.hint { color: #61738c; line-height: 1.7; }
.pager { display: flex; justify-content: flex-end; padding-top: 20px; }
a { color: #245b96; }
</style>
