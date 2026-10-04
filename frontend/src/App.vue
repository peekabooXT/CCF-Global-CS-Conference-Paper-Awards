<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading, Reading } from '@element-plus/icons-vue'
import { api, errMsg } from './api.js'
import SearchView from './views/SearchView.vue'
import CollectView from './views/CollectView.vue'
import ReviewView from './views/ReviewView.vue'
import CoverageView from './views/CoverageView.vue'
import AwardEventsView from './views/AwardEventsView.vue'
import SourceListingsView from './views/SourceListingsView.vue'
const active = ref('search')
const settingsDialogVisible = ref(false)
const importing = ref(false)
const searchVersion = ref(0)

const AI_SETTINGS_KEY = 'ccf-awards-ai-settings'
const providers = [
  { id: 'deepseek', label: 'DeepSeek', base: 'https://api.deepseek.com', model: 'deepseek-flash', models: ['deepseek-flash', 'deepseek-v4-pro'] },
  { id: 'openai', label: 'OpenAI', base: 'https://api.openai.com/v1', model: 'gpt-5-mini', models: ['gpt-5-mini', 'gpt-5', 'gpt-4.1-mini'] },
  { id: 'bailian', label: '阿里云百炼', base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen3.8-max', models: ['qwen3.8-max', 'qwen3.7-max', 'qwen3.5-plus'] },
  { id: 'qwen', label: '阿里千问（百炼 API）', base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen3.8-max', models: ['qwen3.8-max', 'qwen3.8-flash', 'qwen3.7-plus'] },
  { id: 'zhipu', label: '智谱 GLM', base: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4.6', models: ['glm-5.1', 'glm-5', 'glm-4.7', 'glm-4.6'] },
  { id: 'custom', label: '中转站／自定义 OpenAI 兼容接口', base: '', model: '', models: [] },
]
const defaultAiSettings = {
  llm: { provider: 'deepseek', base_url: 'https://api.deepseek.com', model: 'deepseek-flash', api_key: '', json_mode: true },
}

function loadAiSettings() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(AI_SETTINGS_KEY) || '{}')
    return {
      llm: { ...defaultAiSettings.llm, ...(saved.llm || {}) },
    }
  } catch {
    return {
      llm: { ...defaultAiSettings.llm },
    }
  }
}

const aiSettings = reactive(loadAiSettings())
const hasSessionSettings = computed(() => Boolean(aiSettings.llm.api_key))
const currentProvider = computed(() => providers.find(item => item.id === aiSettings.llm.provider) || providers[5])
const fetchedModels = ref([])
const modelsLoading = ref(false)
const modelOptions = computed(() => {
  const liveById = new Map(fetchedModels.value.map(item => [item.id, item]))
  const ids = [aiSettings.llm.model, ...currentProvider.value.models, ...liveById.keys()].filter(Boolean)
  return [...new Set(ids)].map(id => ({ id, live: liveById.has(id), name: liveById.get(id)?.name }))
})

function onProviderChange(provider) {
  const profile = providers.find(item => item.id === provider)
  if (!profile) return
  aiSettings.llm.base_url = profile.base
  aiSettings.llm.model = profile.model
  aiSettings.llm.api_key = ''
  fetchedModels.value = []
  ElMessage.info('已切换提供商；请填写该账户的 API Key，旧 Key 不会复用')
}

async function refreshModels() {
  const connection = { ...aiSettings.llm }
  modelsLoading.value = true
  try {
    const result = await api.llmModels(connection)
    if (connection.provider !== aiSettings.llm.provider || connection.api_key !== aiSettings.llm.api_key ||
        connection.base_url !== aiSettings.llm.base_url) return
    fetchedModels.value = result.models || []
    ElMessage.success(`已获取 ${fetchedModels.value.length} 个当前账户可见模型；联网搜索能力仍以实际接口为准`)
  } catch (error) { ElMessage.warning(errMsg(error)) }
  finally { modelsLoading.value = false }
}

watch(aiSettings, value => {
  try {
    sessionStorage.setItem(AI_SETTINGS_KEY, JSON.stringify(value))
  } catch {
    // Privacy-restricted browsers may disable session storage; in-memory state still works.
  }
}, { deep: true })

function openSettings() {
  settingsDialogVisible.value = true
}
async function importDemo() {
  importing.value = true
  try { await api.demo(); searchVersion.value++; active.value='search'; ElMessage.success('两条样例已导入，重复记录不会重复添加。') }
  catch(e) { ElMessage.error(errMsg(e)) }
  finally { importing.value=false }
}
const meta = ref(null)
const loading = ref(true)
const loadError = ref('')
const navigation = [{id:'search',label:'论文检索'},{id:'events',label:'获奖事件'},{id:'listings',label:'来源收录'},{id:'collect',label:'采集与导入'},{id:'review',label:'记录核验'},{id:'coverage',label:'采集覆盖'}]
async function boot() {
  loading.value = true
  loadError.value = ''
  try { meta.value = await api.meta() }
  catch(e) { loadError.value = errMsg(e) }
  finally { loading.value = false }
}
onMounted(boot)
</script>

<template>
  <div class="academic-app">
    <header class="site-header">
      <div class="header-inner">
        <a class="brand" href="#" @click.prevent="active = 'search'" aria-label="Global CS Paper Awards Agent 首页">
          <span class="brand-mark"><el-icon :size="25"><Reading /></el-icon></span>
          <span><strong>Global CS Paper Awards Agent</strong><small>计算机领域获奖论文资料库</small></span>
        </a>
        <nav aria-label="主导航">
          <button v-for="item in navigation" :key="item.id" :class="{active:active===item.id}" :aria-current="active===item.id?'page':undefined" @click="active=item.id">{{ item.label }}</button>
        </nav>
      </div>
    </header>
    <main class="main-shell">
      <div v-if="loading" class="center-state" role="status"><el-icon class="is-loading" :size="24"><Loading /></el-icon><p>正在加载论文资料库…</p></div>
      <div v-else-if="!meta" class="center-state" role="alert"><h2>暂时无法连接资料库</h2><p>{{ loadError }}</p><el-button type="primary" @click="boot">重新连接</el-button></div>
      <template v-else>
        <div class="utility-bar" aria-label="设置与数据工具">
          <span>资料库工具</span>
          <el-button @click="openSettings">
            LLM 连接
            <el-tag v-if="hasSessionSettings" type="success" size="small" effect="plain" class="configured-tag">已配置</el-tag>
          </el-button>
          <el-button :loading="importing" @click="importDemo">导入两条样例</el-button>
        </div>
        <SearchView :key="searchVersion" v-if="active==='search'" :meta="meta" />
        <AwardEventsView v-else-if="active==='events'" :meta="meta" />
        <SourceListingsView v-else-if="active==='listings'" />
        <section v-else class="workspace-panel">
          <CollectView v-if="active==='collect'" :meta="meta" :ai-settings="aiSettings" />
          <ReviewView v-else-if="active==='review'" :meta="meta" />
          <CoverageView v-else :meta="meta" />
        </section>
      </template>
    </main>

    <el-dialog v-model="settingsDialogVisible" title="LLM 连接" width="760px" class="ai-settings-dialog">
      <p class="settings-hint">配置只保存在当前浏览器标签页的会话中。切换功能页面或刷新后仍可继续使用，关闭标签页后自动清除。</p>
      <p class="settings-hint">搜索与提取共用当前连接的 Key 和模型；切换提供商会清空旧 Key。使用非官方服务时请选择“中转站／自定义 OpenAI 兼容接口”。</p>
      <el-form label-position="top">
        <div class="settings-grid">
          <el-form-item label="提供商">
            <el-select v-model="aiSettings.llm.provider" style="width:100%" @change="onProviderChange">
              <el-option v-for="item in providers" :key="item.id" :label="item.label" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="模型">
            <el-select v-model="aiSettings.llm.model" filterable allow-create default-first-option style="width:100%" placeholder="选择或手动输入模型 ID">
              <el-option v-for="item in modelOptions" :key="item.id" :label="item.id + (item.live ? ` · ${item.name || '当前账户'}` : '')" :value="item.id" />
            </el-select>
            <el-button size="small" text :loading="modelsLoading" @click="refreshModels">读取此连接可用模型</el-button>
          </el-form-item>
          <el-form-item label="API 地址" class="settings-full">
            <el-input v-model="aiSettings.llm.base_url" :placeholder="aiSettings.llm.provider === 'custom' ? 'https://你的中转站域名/v1' : currentProvider.base" />
          </el-form-item>
          <el-form-item label="API Key" class="settings-full">
            <el-input v-model="aiSettings.llm.api_key" type="password" show-password autocomplete="new-password" />
          </el-form-item>
        </div>
        <el-checkbox v-model="aiSettings.llm.json_mode">启用 JSON 模式</el-checkbox>
      </el-form>
      <el-alert v-if="(aiSettings.llm.base_url || 'https://api.deepseek.com').includes('api.deepseek.com') && aiSettings.llm.provider === 'deepseek'" type="warning" :closable="false" show-icon title="使用 DeepSeek 官方连接自动搜索时，搜索和提取都向当前 DeepSeek Key 计费；搜索可能额外产生模型 Token 费用。批量采集会逐项调用。" />
      <el-alert v-if="aiSettings.llm.provider === 'zhipu'" type="info" :closable="false" show-icon title="智谱自动搜索使用当前模型的 web_search 工具；部分 GLM 模型可能不支持，请以实际返回的来源为准，也可改用已有官网网址。" />
      <el-alert v-if="aiSettings.llm.provider === 'custom'" type="info" :closable="false" show-icon title="中转站需提供 OpenAI 兼容的 /chat/completions 接口用于提取。自动搜索还需同一地址提供 Responses /responses 的 web_search 工具并返回可核验来源；如果不支持，请在采集页选择“使用各会议年度已保存网址”。" />
      <p v-if="aiSettings.llm.provider === 'custom'" class="settings-hint">填写中转站的公共 HTTPS 基础地址（通常以 /v1 结尾，不要填 /chat/completions）、该站发放的 Key 和模型 ID。可尝试读取 /models；若中转站不提供模型列表，仍可手动输入模型。JSON 模式不兼容时可取消勾选。</p>
      <p class="settings-hint">模型预设仅供快速选择，不保证当前账户已开通或支持网页搜索；可读取账户列表，也可直接手填模型 ID。百炼和千问使用同一阿里云百炼 Key。</p>

      <template #footer>
        <el-button type="primary" @click="settingsDialogVisible = false">完成</el-button>
      </template>
    </el-dialog>

    <footer class="site-footer"><span>Global CS Paper Awards Agent · 学术资料索引</span><span>保留原始来源 · 缺失信息标注未知 · 核验状态可追溯</span></footer>
  </div>
</template>

<style>
:root{font-family:Inter,"Segoe UI","Microsoft YaHei",sans-serif;color:#1f2937;background:#f5f8fc;font-synthesis:none;--el-color-primary:#245c96;--el-color-primary-light-3:#668fb8;--el-color-primary-light-5:#93b0cf;--el-color-primary-light-7:#c7d8e9;--el-color-primary-light-9:#eff5fc;--el-color-primary-dark-2:#174a7e;--el-border-radius-base:6px;--el-text-color-primary:#1f2937;--el-text-color-regular:#45566c;--el-border-color:#dce4ee}
*{box-sizing:border-box}body{margin:0}button,input{font:inherit}button,a{-webkit-tap-highlight-color:transparent}button:focus-visible,a:focus-visible{outline:3px solid #90b8e6;outline-offset:3px}a{color:#245c96}h1,h2,h3{color:#163a60}h2{font-size:22px}p{line-height:1.65}.academic-app{min-height:100vh;display:flex;flex-direction:column}.site-header{background:white;border-top:4px solid #174a7e;border-bottom:1px solid #dce4ee}.header-inner{max-width:1440px;margin:auto;min-height:86px;padding:0 40px;display:flex;align-items:center;justify-content:space-between;gap:28px}.brand{display:flex;gap:12px;align-items:center;text-decoration:none;flex-shrink:0}.brand-mark{background:#174a7e;color:white;width:43px;height:46px;border-radius:6px;display:grid;place-items:center}.brand strong{font-family:Georgia,"Times New Roman",serif;font-size:23px;display:block;color:#163a60}.brand small{display:block;color:#62748a;font-size:12px;margin-top:4px;letter-spacing:1px}nav{display:flex;align-self:stretch;gap:22px}nav button{background:none;border:0;border-bottom:3px solid transparent;color:#52657a;padding:0 6px;cursor:pointer;white-space:nowrap;font-size:14px}nav button:hover{color:#174a7e}nav button.active{color:#174a7e;border-bottom-color:#245c96;font-weight:600}.main-shell{width:100%;max-width:1440px;padding:36px 40px 48px;margin:0 auto;flex:1}.workspace-panel{background:white;border:1px solid #dce4ee;border-radius:8px;padding:28px;overflow:auto}.workspace-panel h2{margin-top:0}.hint{color:#62748a!important}.center-state{text-align:center;padding:80px 20px;color:#62748a}.utility-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:22px}.utility-bar>span{font-size:12px;color:#62748a;margin-right:8px}.utility-bar .el-button{margin-left:0}.site-footer{max-width:1440px;width:100%;padding:22px 40px;margin:auto;border-top:1px solid #dce4ee;display:flex;justify-content:space-between;gap:16px;color:#64748b;font-size:12px}.el-table{--el-table-header-bg-color:#f1f6fc;--el-table-row-hover-bg-color:#f5f8fc}.el-drawer{max-width:100vw}.el-drawer__header{padding-bottom:18px;margin-bottom:0;border-bottom:1px solid #dce4ee}.el-drawer__body{padding:26px}.detail h3{line-height:1.5;font-family:Georgia,"Microsoft YaHei",serif;font-size:23px}.el-form-item__label{color:#45566c}.el-button{font-weight:500}
@media(max-width:900px){.header-inner{padding:18px 22px 0;flex-wrap:wrap;gap:16px}nav{min-height:48px;gap:18px;overflow:auto}.main-shell{padding:24px 20px}.utility-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:22px}.utility-bar>span{font-size:12px;color:#62748a;margin-right:8px}.utility-bar .el-button{margin-left:0}.site-footer{padding:20px;flex-wrap:wrap}.brand strong{font-size:21px}.workspace-panel{padding:18px}}
/* Primary navigation has its own centered row; tools remain secondary. */
.header-inner{display:flex;flex-direction:column;align-items:stretch;gap:0;padding-top:20px}
.brand{align-self:flex-start;margin-bottom:14px}
.site-header nav{justify-content:center;gap:32px;min-height:52px;border-top:1px solid #edf1f6;flex-wrap:wrap}
.site-header nav button{min-height:48px;padding:0 18px;font-size:15px}
.utility-bar{justify-content:flex-end;margin-bottom:18px}
.configured-tag{margin-left:8px;vertical-align:middle}
.settings-hint{margin:0;color:#62748a;font-size:13px}
.settings-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 18px}
.settings-full{grid-column:1/-1}
.ai-settings-dialog{max-width:calc(100vw - 32px)}
:root{--el-text-color-placeholder:#65758a}
@media(max-width:650px){.site-header nav{gap:0}.site-header nav button{padding:0 12px;font-size:14px}.utility-bar{justify-content:flex-start}.header-inner{padding-top:16px}.brand strong{font-size:20px}.settings-grid{grid-template-columns:1fr}.settings-full{grid-column:auto}}
/* A calmer blue-and-white visual system, shared by the existing pages. */
:root{--el-color-primary:#1476d4;--el-color-primary-light-3:#58a0e6;--el-color-primary-light-5:#8fc0ee;--el-color-primary-light-7:#c4def6;--el-color-primary-light-9:#eef7ff;--el-color-primary-dark-2:#0d5eaa;--el-border-color:#dce7f3}
body{background:#f6f9fd}.site-header{border-top:0;border-bottom:1px solid #e3ecf6;box-shadow:0 2px 14px rgba(25,70,126,.035)}
.header-inner{max-width:1600px;padding:16px 38px 0}.brand{margin-bottom:15px}.brand-mark{background:linear-gradient(135deg,#1584e6,#1054a9);border-radius:11px;width:45px;height:45px;box-shadow:0 6px 14px rgba(20,118,212,.18)}
.brand strong{font-family:Inter,"Segoe UI","Microsoft YaHei",sans-serif;font-size:22px;letter-spacing:-.02em;color:#102f59}.brand small{letter-spacing:.02em;color:#7b8fa8}
.site-header nav{border-top-color:#edf2f8;gap:12px}.site-header nav button{color:#607793;border-bottom-width:3px;border-radius:6px 6px 0 0}.site-header nav button:hover{color:#1476d4;background:#f6faff}.site-header nav button.active{color:#1167b6;border-bottom-color:#1782e5;background:#f3f9ff}
.main-shell{max-width:1600px;padding:26px 38px 52px}.utility-bar{margin-bottom:18px}.utility-bar>span{color:#8a9ab0}.utility-bar .el-button{border-radius:8px}.workspace-panel{border-color:#dce7f3;border-radius:12px;box-shadow:0 7px 22px rgba(27,65,111,.035)}.site-footer{max-width:1600px}
@media(max-width:760px){.header-inner{padding:15px 18px 0}.main-shell{padding:18px 14px 38px}.site-header nav{justify-content:flex-start;overflow-x:auto;flex-wrap:nowrap}.site-header nav button{min-height:44px;padding:0 10px}}
@media(max-width:760px){.brand{min-width:0;max-width:100%;flex-shrink:1}.brand>span:last-child{min-width:0}.brand strong{font-size:17px;line-height:1.25;overflow-wrap:anywhere}.brand small{font-size:10px}.site-header nav{min-width:0;max-width:100%}}
</style>


