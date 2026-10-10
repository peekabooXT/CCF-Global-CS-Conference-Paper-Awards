<script setup>
import { ref,computed,watch } from 'vue'
import { ElMessage,ElMessageBox } from 'element-plus'
import { api,errMsg } from '../api.js'
const props=defineProps({modelValue:Boolean})
const emit=defineEmits(['update:modelValue','changed'])
const visible=computed({get:()=>props.modelValue,set:v=>emit('update:modelValue',v)})
const preview=ref(null),loading=ref(false),busy=ref(false),reviewer=ref(''),error=ref(''),choices=ref({}),last=ref(null)
const statusLabel=s=>({verified:'已核验',pending:'待核验',rejected:'已排除'}[s]||s)
async function scan(){
  loading.value=true
  try{
    preview.value=await api.duplicates();error.value='';choices.value={}
    for(const g of preview.value.groups) choices.value[g.id]={keep_id:g.recommended_id,mode:'merge',delete_ids:g.members.filter(r=>r.id!==g.recommended_id).map(r=>r.id)}
  }catch(e){error.value=errMsg(e)}finally{loading.value=false}
}
watch(visible,v=>{if(v)scan()})
function keepChanged(group){ choices.value[group.id].delete_ids=group.members.filter(r=>r.id!==choices.value[group.id].keep_id).map(r=>r.id) }
async function resolve(group=null){
  if(!reviewer.value.trim()){ElMessage.warning('请填写处理人');return}
  const choice=group?choices.value[group.id]:null
  const count=group?choice.delete_ids.length:preview.value.groups.filter(g=>g.auto_safe).reduce((n,g)=>n+g.members.length-1,0)
  if(!count){ElMessage.warning('请选择需要处理的记录');return}
  const deletion=choice?.mode==='delete'
  try{
    await ElMessageBox.confirm(deletion
      ?`将删除选中的 ${count} 条实体及其关联来源／获奖记录，不保留这些关联。操作前自动备份完整数据库。确认删除？`
      :`将移除 ${count} 条重复实体，保留选定记录并合并所有获奖和来源关联。不同核验状态不自动合并，操作前自动备份。确认继续？`,
      deletion?'确认删除选中数据':'确认合并重复数据',{type:deletion?'warning':'info',confirmButtonText:deletion?'确认删除':'确认合并',cancelButtonText:'取消'})
  }catch{return}
  busy.value=true
  try{
    last.value=await api.resolveDuplicates({digest:preview.value.digest,reviewer:reviewer.value,
      confirmed:true,auto:!group,decisions:group?[{group_id:group.id,...choice}]:[]})
    ElMessage.success(`已处理 ${last.value.groups} 组，移除 ${last.value.removed} 条重复实体`)
    emit('changed');await scan()
  }catch(e){ElMessage.error(errMsg(e));await scan()}finally{busy.value=false}
}
</script>
<template>
  <el-dialog v-model="visible" title="本地重复数据排查" width="1100px" align-center class="duplicate-dialog" style="max-width:calc(100vw - 28px)">
    <p class="hint">只匹配同一会议、年份和规范化题名，不做模糊自动删除。论文实体重复与同奖项采集记录重复分开处理；一篇论文的多个奖项和来源不是重复论文，合并时全部保留。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div class="duplicate-tools"><el-input v-model="reviewer" placeholder="处理人（必填）" aria-label="重复处理人" style="width:200px" /><el-button :loading="loading" :disabled="busy" @click="scan">重新扫描</el-button><el-button type="primary" :disabled="!preview?.auto_safe_groups||busy||loading" @click="resolve()">一键合并已核验重复</el-button></div>
    <p v-if="preview" role="status">发现 {{ preview.group_count }} 组重复，共 {{ preview.extra_rows }} 条多余实体；其中 {{ preview.auto_safe_groups }} 组可安全一键合并。</p>
    <el-alert v-if="last?.backup" type="success" :closable="false" :title="`处理前完整备份：${last.backup}`" />
    <el-empty v-if="preview&&!preview.groups.length" description="未发现重复实体" />
    <el-collapse v-if="preview" class="duplicate-groups">
      <el-collapse-item v-for="g in preview.groups" :key="g.id" :name="g.id">
        <template #title><span>{{ g.venue }} · {{ g.year }} · {{ g.title }} <small>（{{ g.kind==='paper'?'论文实体':'同奖项采集记录' }}，{{ g.members.length }} 条）</small></span></template>
        <div class="group-tools"><el-select v-model="choices[g.id].mode" aria-label="处理方式" style="width:230px"><el-option value="merge" label="保留选定记录并合并关联" /><el-option value="delete" label="删除选中数据（不合并）" /></el-select><el-button :disabled="busy||loading" :type="choices[g.id].mode==='delete'?'danger':'primary'" @click="resolve(g)">{{ choices[g.id].mode==='delete'?'删除选中数据':'合并选中重复' }}</el-button></div>
        <el-radio-group v-model="choices[g.id].keep_id" @change="keepChanged(g)" class="member-list">
          <div v-for="r in g.members" :key="r.id" class="duplicate-member">
            <div class="member-choices"><el-radio v-if="choices[g.id].mode==='merge'" :value="r.id">保留此记录</el-radio><el-checkbox v-model="choices[g.id].delete_ids" :value="r.id" :disabled="choices[g.id].mode==='merge'&&choices[g.id].keep_id===r.id">移除此记录</el-checkbox><el-tag v-if="r.id===g.recommended_id" size="small">建议保留</el-tag></div>
            <strong>{{ r.title }}</strong><p>ID：{{ r.id }} · 核验状态：{{ r.statuses.map(statusLabel).join(' / ') }}</p><p>作者：{{ r.authors_raw || '未知' }}</p><p>奖项：{{ r.awards.map(a=>a.official_award_name || '来源未提供原名').join('；') || '来源收录' }}</p><p>论文链接：{{ r.paper_url || '未提供' }}</p><p v-for="url in r.sources" :key="url">来源：{{ url }}</p>
          </div>
        </el-radio-group>
      </el-collapse-item>
    </el-collapse>
    <p class="hint">“合并”只移除多余实体 ID 并迁移全部关联；“删除”会删除该实体的关联，请仔细对比。修改后须再次审核发布，服务器不会被本地按钮即时修改。</p>
  </el-dialog>
</template>
<style scoped>
.duplicate-tools,.group-tools,.member-choices{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:12px 0}.duplicate-tools .el-button,.group-tools .el-button{margin:0}.hint,small{color:#71849b;font-size:12px}.duplicate-groups{margin-top:12px}.member-list{display:grid;width:100%;gap:10px}.duplicate-member{padding:12px 16px;border:1px solid #dce7f4;background:#f8fbff;border-radius:7px;overflow-wrap:anywhere}.duplicate-member p{font-size:12px;color:#526b88;margin:4px 0;line-height:1.5}.duplicate-member strong{font-size:13px}.member-choices{margin:0 0 8px}:deep(.el-collapse-item__header){height:auto;min-height:48px;line-height:1.5;padding:8px 0}:global(.duplicate-dialog .el-dialog__body){max-height:calc(100vh - 150px);overflow:auto}
</style>
