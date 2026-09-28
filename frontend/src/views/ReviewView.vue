<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api.js'
import RecordDetail from '../components/RecordDetail.vue'

const props = defineProps({ meta: { type: Object, required: true } })

const statusOptions = ['pending', 'verified', 'rejected', 'all']
const filter = ref('pending')
const records = ref([])
const selectedId = ref(null)
const loading = ref(false)
const saving = ref(false)

const form = ref({ reviewer: '', note: '' })

async function load() {
  loading.value = true
  try {
    const res = await api.search({ status: filter.value })
    records.value = res.records
    selectedId.value = records.value[0]?.id || null
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    loading.value = false
  }
}

onMounted(load)

const selected = computed(() => records.value.find(r => r.id === selectedId.value))

async function save() {
  if (!selected.value) return
  saving.value = true
  try {
    await api.review({
      id: selected.value.id,
      state: form.value.state || selected.value.status,
      reviewer: form.value.reviewer,
      note: form.value.note,
    })
    ElMessage.success('核验结论已保存')
    await load()
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div>
    <h2>记录核验</h2>
    <p class="hint">核对来源中的奖项、作者与单位对应关系后，更新记录状态。</p>

    <div class="bar">
      <el-select v-model="filter" style="width: 160px" @change="load">
        <el-option v-for="s in statusOptions" :key="s" :label="meta.statuses[s]" :value="s" />
      </el-select>
      <el-select
        v-model="selectedId" placeholder="选择要核验的论文" style="width: 420px"
        :disabled="!records.length"
      >
        <el-option
          v-for="r in records" :key="r.id"
          :label="`${r.acronym} ${r.year} · ${r.title}`" :value="r.id"
        />
      </el-select>
    </div>

    <el-empty v-if="!records.length && !loading" description="当前状态下没有记录" />

    <div v-else-if="selected" class="grid">
      <div>
        <RecordDetail :record="selected" :awards="meta.awards" />
      </div>
      <el-card class="review-card" shadow="never">
        <h4>核验结论</h4>
        <el-form :model="form" label-width="80px">
          <el-form-item label="核验状态">
            <el-select v-model="form.state" :default-value="selected.status" style="width: 100%">
              <el-option label="待核验" value="pending" />
              <el-option label="已核验" value="verified" />
              <el-option label="已排除" value="rejected" />
            </el-select>
          </el-form-item>
          <el-form-item label="核验人">
            <el-input v-model="form.reviewer" placeholder="你的名字" />
          </el-form-item>
          <el-form-item label="核验备注">
            <el-input v-model="form.note" type="textarea" :rows="4" placeholder="记录依据、缺失信息或需要更正的内容" />
          </el-form-item>
          <el-button type="primary" :loading="saving" @click="save">保存核验结论</el-button>
        </el-form>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
h2 { margin: 0; }
.hint { color: #8494a8; font-size: 13px; }
.bar { display: flex; gap: 12px; margin: 12px 0; }
.grid { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; }
.review-card { align-self: start; }
</style>
