<script setup>
defineProps({
  record: { type: Object, required: true },
  awards: { type: Object, required: true },
})
</script>

<template>
  <div class="detail">
    <h3 class="r-title">{{ record.title }}</h3>
    <el-descriptions :column="3" size="small" border>
      <el-descriptions-item label="会议">
        {{ record.acronym }} {{ record.year }} · CCF {{ record.rank }}
      </el-descriptions-item>
      <el-descriptions-item label="奖项">{{ awards[record.award_type] }}</el-descriptions-item>
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
    <el-alert v-else type="info" :title="'来源尚未提供作者信息'" :closable="false" />

    <h4>来源</h4>
    <div v-for="(s, i) in record.sources" :key="s.id" class="src">
      <el-link :href="s.url" target="_blank" type="primary">
        来源 {{ i + 1 }} · {{ s.role === 'award' ? '获奖页面' : '论文元数据' }}
      </el-link>
    </div>
    <el-link v-if="record.paper_url" :href="record.paper_url" target="_blank" type="success">
      打开论文
    </el-link>

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
.review-note { margin-top: 12px; color: #5a6b82; font-size: 13px; }
.raw {
  background: #f6f8fa; padding: 8px; border-radius: 4px;
  font-size: 12px; max-height: 320px; overflow: auto;
}
</style>
