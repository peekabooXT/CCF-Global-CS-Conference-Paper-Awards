<script setup>
import { t } from '../i18n.js'
import { PAGE_SIZES } from '../pagination.js'

defineProps({
  page: { type: Number, default: 1 },
  pageSize: { type: Number, default: 5 },
  total: { type: Number, default: 0 },
  disabled: Boolean,
})
const emit = defineEmits(['update:page', 'update:pageSize'])
function changeSize(size) {
  emit('update:pageSize', size)
  emit('update:page', 1)
}
</script>

<template>
  <div v-if="total" class="paper-pagination" role="navigation" :aria-label="t(&quot;论文分页&quot;)">
    <el-pagination
      :current-page="page" :page-size="pageSize" :page-sizes="PAGE_SIZES" :total="total"
      :disabled="disabled" :pager-count="5" layout="total, sizes, prev, pager, next, jumper"
      @update:current-page="emit('update:page', $event)" @update:page-size="changeSize"
    />
  </div>
</template>

<style scoped>
.paper-pagination{display:flex;justify-content:flex-end;padding:16px 0 0;border-top:1px solid #e7edf5;margin-top:16px}
.paper-pagination :deep(.el-pagination){display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px 0;max-width:100%}
.paper-pagination :deep(.el-pagination__sizes){margin-right:16px}.paper-pagination :deep(.el-pagination__jump){margin-left:16px}
@media(max-width:760px){
  .paper-pagination{justify-content:center}
  .paper-pagination :deep(.el-pagination){display:grid;grid-template-columns:32px minmax(0,1fr) 32px;gap:12px 0;width:100%;max-width:360px}
  .paper-pagination :deep(.el-pagination__total){grid-area:1/1/2/3;justify-self:start;margin:0}
  .paper-pagination :deep(.el-pagination__sizes){grid-area:1/2/2/4;justify-self:end;margin:0}
  .paper-pagination :deep(.btn-prev){grid-area:2/1;margin:0}
  .paper-pagination :deep(.el-pager){grid-area:2/2;justify-content:center}
  .paper-pagination :deep(.btn-next){grid-area:2/3;margin:0}
  .paper-pagination :deep(.el-pagination__jump){grid-area:3/1/4/4;justify-self:center;margin:0}
}
</style>
