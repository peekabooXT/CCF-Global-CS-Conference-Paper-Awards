<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api.js'

const props = defineProps({ meta: { type: Object, required: true } })
const conferences = computed(() => props.meta?.conferences || [])
const awardKeys = computed(() => Object.keys(props.meta?.awards || {}))
const stateKeys = computed(() => Object.keys(props.meta?.coverage || {}))

const today = new Date().getFullYear()
const query = reactive({ cid: null, start: 2024, end: today })
const rows = ref([])
const loading = ref(false)

const markForm = reactive({
  conference_id: null, year: 2024, award: null, state: 'partial', url: '', note: '',
})

async function load() {
  loading.value = true
  try {
    const res = await api.coverage({ start: query.start, end: query.end, cid: query.cid || null })
    rows.value = res.rows
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function mark() {
  try {
    await api.markCoverage(markForm)
    ElMessage.success('覆盖结论已保存')
    await load()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}
</script>

<template>
  <div>
    <h2>采集覆盖</h2>
    <p class="hint">按会议、年份和奖项分别检查。没有找到记录，不等于该年度没有设奖。</p>

    <el-form inline>
      <el-form-item label="会议范围">
        <el-select v-model="query.cid" clearable placeholder="全部" style="width: 260px">
          <el-option v-for="c in conferences" :key="c.id" :label="`${c.acronym} · ${c.area}`" :value="c.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="年份">
        <el-input-number v-model="query.start" :min="1900" :max="2200" controls-position="right" style="width: 110px" />
        <span> – </span>
        <el-input-number v-model="query.end" :min="1900" :max="2200" controls-position="right" style="width: 110px" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="loading" @click="load">查看覆盖情况</el-button>
      </el-form-item>
    </el-form>

    <el-table :data="rows" v-loading="loading" border size="small" max-height="520">
      <el-table-column prop="acronym" label="会议" width="110" />
      <el-table-column prop="rank" label="CCF" width="70" />
      <el-table-column prop="year" label="年份" width="80" />
      <el-table-column label="奖项" width="160">
        <template #default="{ row }">{{ meta.awards[row.award_type] }}</template>
      </el-table-column>
      <el-table-column label="覆盖状态" width="120">
        <template #default="{ row }">{{ meta.coverage[row.state] }}</template>
      </el-table-column>
      <el-table-column label="待核验" width="90">
        <template #default="{ row }">{{ row.counts?.pending || 0 }}</template>
      </el-table-column>
      <el-table-column label="已核验" width="90">
        <template #default="{ row }">{{ row.counts?.verified || 0 }}</template>
      </el-table-column>
      <el-table-column prop="note" label="备注" min-width="160" show-overflow-tooltip />
    </el-table>

    <el-divider>记录人工检查结论</el-divider>
    <el-form :model="markForm" inline>
      <el-form-item label="会议">
        <el-select v-model="markForm.conference_id" style="width: 240px">
          <el-option v-for="c in conferences" :key="c.id" :label="`${c.acronym} · ${c.area}`" :value="c.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="年份">
        <el-input-number v-model="markForm.year" :min="1900" :max="2200" controls-position="right" style="width: 110px" />
      </el-form-item>
      <el-form-item label="奖项">
        <el-select v-model="markForm.award" style="width: 160px">
          <el-option v-for="k in awardKeys" :key="k" :label="meta.awards[k]" :value="k" />
        </el-select>
      </el-form-item>
      <el-form-item label="结论">
        <el-select v-model="markForm.state" style="width: 150px">
          <el-option v-for="k in stateKeys" :key="k" :label="meta.coverage[k]" :value="k" />
        </el-select>
      </el-form-item>
      <el-form-item label="来源网址">
        <el-input v-model="markForm.url" placeholder="https://…" style="width: 240px" />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="markForm.note" placeholder="检查备注" style="width: 240px" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="mark">保存覆盖结论</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<style scoped>
h2 { margin: 0; }
.hint { color: #8494a8; font-size: 13px; }
</style>
