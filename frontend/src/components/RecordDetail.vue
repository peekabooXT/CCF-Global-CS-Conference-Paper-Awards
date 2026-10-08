<script setup>
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { api, errMsg } from '../api.js'

const props = defineProps({
  record: { type: Object, required: true },
  awards: { type: Object, required: true },
})
const provenance = ref(null)
const sourceLoading = ref(false)
const sourceError = ref('')
let requestVersion = 0
async function loadSources() {
  const version = ++requestVersion
  provenance.value = null
  sourceError.value = ''
  sourceLoading.value = true
  try {
    const result = await api.paperSources(props.record.id)
    if (version === requestVersion) provenance.value = result
  } catch (error) {
    if (version === requestVersion) sourceError.value = errMsg(error)
  } finally {
    if (version === requestVersion) sourceLoading.value = false
  }
}
watch(() => props.record.id, loadSources, { immediate: true })
onBeforeUnmount(() => { requestVersion++ })
const listings = computed(() => provenance.value?.listings || [])
const baseSources = computed(() => {
  const seen = new Set()
  return (props.record.sources || []).filter(source => {
    if (source.role === 'listing' && listings.value.some(item => item.source_url === source.url)) return false
    const key = `${source.role}:${source.url}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
})
const statusLabel = status => ({ verified: '已核验', pending: '待核验', rejected: '已拒绝' }[status] || status)
</script>

<template>
  <div class="detail">
    <h3 class="r-title">{{ record.title }}</h3>
    <el-descriptions :column="3" size="small" border>
      <el-descriptions-item label="会议">
        {{ record.acronym }} {{ record.year }} · CCF {{ record.rank || '未映射' }}
      </el-descriptions-item>
      <el-descriptions-item label="统一分类">{{ record.category_label || '其他获奖' }}</el-descriptions-item>
      <el-descriptions-item label="奖项原名">{{ record.award_name || (record.source_kind === 'source_listing' ? '来源未提供' : awards[record.award_type] || '未提供') }}</el-descriptions-item>
      <el-descriptions-item label="状态">{{ record.status }}</el-descriptions-item>
      <el-descriptions-item label="发表日期">
        {{ record.publication_date || '未知' }}
      </el-descriptions-item>
    </el-descriptions>

    <h4>作者及单位</h4>
    <el-table v-if="record.authors?.length" :data="record.authors" size="small" border>
      <el-table-column prop="name" label="作者" />
      <el-table-column label="发表时单位">
        <template #default="{ row }">
          {{ row.affiliations?.map(a => a.name).join('；') || '未知' }}
        </template>
      </el-table-column>
    </el-table>
    <p v-else-if="record.authors_raw">{{ record.authors_raw }}</p>
    <el-alert v-else type="info" :title="'来源尚未提供作者信息'" :closable="false" />

    <h4>来源与收录依据</h4>
    <div v-for="(s, i) in baseSources" :key="`${s.role}:${s.url}`" class="src">
      <el-link :href="s.url" target="_blank" rel="noopener noreferrer" type="primary">
        来源 {{ i + 1 }} · {{ s.role === 'award' ? '获奖页面' : s.role === 'listing' ? '聚合收录（未提供逐条奖名）' : '论文元数据' }}
      </el-link>
    </div>
    <el-link v-if="record.paper_url" :href="record.paper_url" target="_blank" rel="noopener noreferrer" type="success">
      打开论文
    </el-link>

    <p v-if="sourceLoading" class="source-hint" role="status">正在读取关联来源…</p>
    <div v-else-if="sourceError" class="source-error" role="alert">
      <span>关联来源暂时加载失败：{{ sourceError }}</span>
      <el-button link type="primary" @click="loadSources">重试</el-button>
    </div>
    <template v-else-if="listings.length">
      <p class="source-hint">以下是聚合网站的收录依据；与官方颁奖证据区分保留，不据此补造奖项原名或重复计算论文。</p>
      <article v-for="item in listings" :key="item.id" class="listing-source">
        <div class="listing-heading">
          <strong>{{ item.source_name === 'jeffhuang' ? 'JeffHuang 最佳论文汇总' : item.source_name }}</strong>
          <el-tag size="small" :type="item.status === 'verified' ? 'success' : 'info'">{{ statusLabel(item.status) }}</el-tag>
        </div>
        <p>{{ item.source_venue }} · {{ item.year }} · 收录条目 {{ item.source_row }}</p>
        <p>来源题名：{{ item.title }}</p>
        <p v-if="item.area_raw">来源领域：{{ item.area_raw }}</p>
        <p v-if="item.authors_raw">作者及单位（来源原文）：{{ item.authors_raw }}</p>
        <div class="listing-links">
          <a :href="item.source_url" target="_blank" rel="noopener noreferrer">打开收录来源 ↗</a>
          <a v-if="item.discovery_url" :href="item.discovery_url" target="_blank" rel="noopener noreferrer">Google Scholar 检索 ↗</a>
        </div>
        <p v-if="item.discovery_url" class="source-hint">Google Scholar 检索链接不是官方授奖证据或论文正文。</p>
        <p v-if="item.linked_awards.length">已关联年度颁奖记录：{{ item.linked_awards.map(award => `${award.venue} ${award.year} · ${award.official_award_name}`).join('；') }}</p>
        <p v-if="item.linked_record_count">已关联现有论文记录：{{ item.linked_record_count }} 条（去重关联，不新增获奖事件）</p>
        <p v-if="!item.linked_awards.length && !item.linked_record_count" class="source-hint">尚未匹配到独立颁奖记录或其他论文记录；这不影响本条收录的核验状态。</p>
      </article>
    </template>

    <div v-if="record.review_note" class="review-note">
      核验人：{{ record.reviewer || '未知' }}<br />
      备注：{{ record.review_note }}
    </div>

    <el-collapse>
      <el-collapse-item title="查看字段证据及原始记录">
        <pre class="raw">{{ JSON.stringify(record, null, 2) }}</pre>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<style scoped>
.r-title { margin: 0 0 8px; }
h4 { margin: 12px 0 6px; }
.src { margin: 2px 0; }
.source-hint { color: #74859b; font-size: 12px; line-height: 1.6; }
.source-error { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; color: #a57118; font-size: 13px; margin-top: 10px; }
.listing-source { padding: 12px 14px; margin-top: 10px; border: 1px solid #dce8f5; border-radius: 7px; background: #f8fbff; overflow-wrap: anywhere; }
.listing-heading { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; font-size: 13px; }
.listing-source p { margin: 6px 0; font-size: 13px; }
.listing-links { display: flex; flex-wrap: wrap; gap: 12px; font-size: 13px; }
.review-note { margin-top: 12px; color: #5a6b82; font-size: 13px; }
.raw {
  background: #f6f8fa; padding: 8px; border-radius: 4px;
  font-size: 12px; max-height: 320px; overflow: auto;
}
</style>
