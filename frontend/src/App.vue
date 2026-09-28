<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading, Reading } from '@element-plus/icons-vue'
import { api, errMsg } from './api.js'
import SearchView from './views/SearchView.vue'
import CollectView from './views/CollectView.vue'
import ReviewView from './views/ReviewView.vue'
import CoverageView from './views/CoverageView.vue'
const active = ref('search')
const settings = ref('')
const settingsRequest = ref(0)
const importing = ref(false)
const searchVersion = ref(0)
function openSettings(section) {
  settings.value = section
  settingsRequest.value++
  active.value = 'collect'
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
const navigation = [{id:'search',label:'论文检索'},{id:'collect',label:'采集与导入'},{id:'review',label:'记录核验'},{id:'coverage',label:'采集覆盖'}]
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
        <a class="brand" href="#" @click.prevent="active = 'search'" aria-label="Global CS Paper Awards 首页">
          <span class="brand-mark"><el-icon :size="25"><Reading /></el-icon></span>
          <span><strong>Global CS Paper Awards</strong><small>计算机领域获奖论文资料库</small></span>
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
          <el-button @click="openSettings('llm')">LLM 连接设置</el-button>
          <el-button @click="openSettings('search')">自动网页搜索设置</el-button>
          <el-button :loading="importing" @click="importDemo">导入两条样例</el-button>
        </div>
        <SearchView :key="searchVersion" v-if="active==='search'" :meta="meta" />
        <section v-else class="workspace-panel">
          <CollectView :settings-section="settings" :settings-request="settingsRequest" v-if="active==='collect'" :meta="meta" />
          <ReviewView v-else-if="active==='review'" :meta="meta" />
          <CoverageView v-else :meta="meta" />
        </section>
      </template>
    </main>
    <footer class="site-footer"><span>Global CS Paper Awards · 学术资料索引</span><span>保留原始来源 · 缺失信息标注未知 · 核验状态可追溯</span></footer>
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
:root{--el-text-color-placeholder:#65758a}
@media(max-width:650px){.site-header nav{gap:0}.site-header nav button{padding:0 12px;font-size:14px}.utility-bar{justify-content:flex-start}.header-inner{padding-top:16px}.brand strong{font-size:20px}}
</style>


