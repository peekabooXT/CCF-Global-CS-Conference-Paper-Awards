<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api.js'
const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'published'])
const visible = computed({get:()=>props.modelValue,set:v=>emit('update:modelValue',v)})
const preview=ref(null), runs=ref([]), reviewer=ref(''), note=ref(''), confirmed=ref(false), emptyConfirmed=ref(false), busy=ref(false), error=ref('')
const labels={preflight:'连接检查',github:'更新 GitHub',server:'上传服务器',completed:'发布完成',partial:'GitHub 已更新，服务器失败',failed:'发布失败'}
const running=computed(()=>runs.value.some(r=>['preflight','github','server'].includes(r.status)))
const total=computed(()=>Object.values(preview.value?.verified||{}).reduce((a,b)=>a+b,0)+(preview.value?.pending_total||0))
let timer
async function refresh() {
  try { const [p,h]=await Promise.all([api.publicationPreview(),api.publicationHistory()]); preview.value=p; runs.value=h.runs; error.value='' }
  catch(e){error.value=errMsg(e)}
}
async function poll() {
  try {
    const previous=running.value; runs.value=(await api.publicationHistory()).runs
    if(previous&&!running.value){ await refresh(); emit('published'); confirmed.value=false }
  } catch(e){error.value=errMsg(e)}
}
watch(visible,async v=>{clearInterval(timer);if(v){confirmed.value=false;emptyConfirmed.value=false;await refresh();timer=setInterval(poll,2000)}})
onUnmounted(()=>clearInterval(timer))
async function publish() {
  busy.value=true
  try {await api.publish({digest:preview.value.digest,reviewer:reviewer.value,note:note.value,confirm_review:confirmed.value,allow_empty:emptyConfirmed.value});await poll();ElMessage.success('发布任务已启动，可查看下方进度')}
  catch(e){ElMessage.error(errMsg(e));await refresh()}
  finally{busy.value=false}
}
</script>
<template>
  <el-dialog v-model="visible" title="本地审核与公开发布" width="860px" style="max-width:calc(100vw - 28px)">
    <p class="hint">只发布已核验论文、获奖事件和来源收录。采集配置、API Key、运行日志、Token 用量、核验工作台和覆盖记录留在本地。</p>
    <el-alert v-if="error" type="error" :title="error" :closable="false" />
    <template v-if="preview">
      <p>目标：{{ preview.configuration.repository }} · {{ preview.configuration.server || '尚未配置服务器' }}</p>
      <el-alert v-if="!preview.configuration.configured || !preview.configuration.public_frontend_ready" type="warning" title="发布连接或公开前端构建尚未准备好，请查看本地发布配置说明。" :closable="false" />
      <div class="publish-counts"><span>待审核论文 <b>{{ preview.pending.records }}</b></span><span>待审核获奖关联 <b>{{ preview.pending.event_papers }}</b></span><span>待审核来源收录 <b>{{ preview.pending.source_listings }}</b></span></div>
      <p>已有已核验数据 {{ Object.values(preview.verified).reduce((a,b)=>a+b,0) }} 条（不同来源可能对应同一论文，发布时统一去重展示）。</p>
      <el-alert v-if="preview.errors.length" type="error" title="以下数据缺少有效证据，暂不能批量审核，请先逐条修正或排除。" :closable="false" />
      <ul v-if="preview.errors.length"><li v-for="item in preview.errors.slice(0,10)" :key="item.id">{{ item.title || item.id }}：{{ item.reason }}</li></ul>
      <el-form label-position="top"><el-form-item label="审核人"><el-input v-model="reviewer" /></el-form-item><el-form-item label="审核 / 发布说明"><el-input v-model="note" type="textarea" :rows="2" /></el-form-item></el-form>
      <el-checkbox v-model="confirmed">我已核对来源与获奖信息，确认将本次全部待审核数据标为已核验并发布</el-checkbox>
      <p class="hint">系统只做结构和证据完整性检查，不能替代你对论文事实的审核。被排除的数据不会发布。服务器使用本次完整快照替换公开数据。</p>
      <el-checkbox v-if="total===0" v-model="emptyConfirmed">本次数据为空，我确认清空服务器公开数据和 GitHub 获奖索引</el-checkbox>
      <p><el-button type="primary" :loading="busy||running" :disabled="!confirmed||!reviewer.trim()||preview.errors.length>0||!preview.configuration.configured||!preview.configuration.public_frontend_ready||(total===0&&!emptyConfirmed)" @click="publish">一键审核并更新服务器和 AWARDS.md</el-button><el-button :disabled="running" @click="refresh">重新读取预览</el-button></p>
    </template>
    <h3>发布记录</h3>
    <el-table :data="runs" max-height="260"><el-table-column label="开始时间" prop="started_at" min-width="180" /><el-table-column label="状态" min-width="160"><template #default="{row}">{{ labels[row.status] || row.status }}</template></el-table-column><el-table-column label="完成时间" prop="finished_at" min-width="180" /><el-table-column label="结果" min-width="200"><template #default="{row}"><a v-if="row.details.github" :href="row.details.github.commit_url" target="_blank" rel="noopener">GitHub 提交</a><span v-if="row.details.error"> {{ row.details.error }}</span><span v-else-if="row.status==='completed'"> · 两端已同步</span><p v-if="row.details.local_sync?.warning">{{ row.details.local_sync.warning }}</p></template></el-table-column></el-table>
  </el-dialog>
</template>
<style scoped>.publish-counts{display:flex;flex-wrap:wrap;gap:20px;padding:16px;background:#f1f7fd;border-radius:8px}.publish-counts b{margin-left:8px;color:#1476d4}.hint{font-size:13px}</style>
