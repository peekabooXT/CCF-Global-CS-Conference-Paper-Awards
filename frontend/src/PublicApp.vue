<script setup>
import { ref, onMounted } from 'vue'
import { Reading } from '@element-plus/icons-vue'
import { api, errMsg } from './api.js'
import SearchView from './views/SearchView.vue'
import PaperOverviewView from './views/PaperOverviewView.vue'
import AwardEventsView from './views/AwardEventsView.vue'
import AcknowledgementFooter from './components/AcknowledgementFooter.vue'
const active = ref('search'), meta = ref(null), error = ref('')
const navigation = [{ id: 'search', label: '论文检索' }, { id: 'overview', label: '论文总览' }, { id: 'events', label: '会议年度颁奖' }]
async function boot() { try { meta.value = await api.meta(); error.value = '' } catch(e) { error.value = errMsg(e) } }
onMounted(boot)
</script>
<template>
  <div class="academic-app">
    <header class="site-header"><div class="header-inner">
      <a href="#" class="brand" @click.prevent="active='search'"><span class="brand-mark"><el-icon :size="26"><Reading /></el-icon></span><span><strong>Global CS Paper Awards Agent</strong><small>计算机领域获奖论文资料库 · 公开只读版</small></span></a>
      <nav aria-label="主导航"><button v-for="item in navigation" :key="item.id" :class="{active:active===item.id}" @click="active=item.id">{{ item.label }}</button></nav>
    </div></header>
    <main class="main-shell">
      <div v-if="!meta" class="center-state"><p>{{ error || '正在加载论文资料库…' }}</p><el-button v-if="error" @click="boot">重新连接</el-button></div>
      <template v-else>
        <p v-if="active==='events'" class="publication-stamp">最近发布：{{ meta.publication?.published_at || '尚未发布' }} · 已核验公开数据</p>
        <SearchView v-if="active==='search'" :meta="meta" />
        <PaperOverviewView v-else-if="active==='overview'" :meta="meta" />
        <AwardEventsView v-else-if="active==='events'" :meta="meta" />
      </template>
    </main>
    <AcknowledgementFooter public-version />
  </div>
</template>
<style>
:root{font-family:Inter,"Segoe UI","Microsoft YaHei",sans-serif;color:#1f2937;background:#f6f9fd;--el-color-primary:#1476d4;--el-color-primary-light-9:#eef7ff;--el-border-color:#dce7f3;--el-text-color-regular:#45566c;--el-text-color-placeholder:#65758a;--el-border-radius-base:6px}*{box-sizing:border-box}body{margin:0}button,input{font:inherit}a{color:#245c96}h1,h2,h3{color:#163a60}p{line-height:1.65}.academic-app{min-height:100vh;display:flex;flex-direction:column}.site-header{background:white;border-bottom:1px solid #e3ecf6;box-shadow:0 2px 14px #19467e09}.header-inner{max-width:1600px;padding:16px 38px 0;margin:auto}.brand{display:flex;gap:12px;align-items:center;text-decoration:none;margin-bottom:15px}.brand-mark{background:linear-gradient(135deg,#1584e6,#1054a9);color:white;border-radius:11px;width:45px;height:45px;display:grid;place-items:center}.brand strong{font-size:22px;color:#102f59;display:block}.brand small{display:block;color:#7b8fa8;font-size:12px;margin-top:4px}nav{display:flex;justify-content:center;gap:12px;border-top:1px solid #edf2f8}nav button{min-height:52px;padding:0 18px;border:0;border-bottom:3px solid transparent;background:none;color:#607793;cursor:pointer}nav button.active{color:#1167b6;border-bottom-color:#1782e5;background:#f3f9ff}.main-shell{width:100%;max-width:1600px;padding:26px 38px 52px;margin:auto;flex:1}.publication-stamp{color:#62748a;font-size:13px;text-align:right;margin:0 0 18px}.site-footer{padding:22px 38px;max-width:1600px;width:100%;margin:auto;border-top:1px solid #dce4ee;color:#64748b;font-size:12px}.center-state{text-align:center;padding:80px 20px}.el-table{--el-table-header-bg-color:#f1f6fc}.el-drawer__header{padding-bottom:18px;margin-bottom:0;border-bottom:1px solid #dce4ee}.el-drawer__body{padding:26px}.detail h3{font-size:23px;line-height:1.5}.hint{color:#62748a}@media(max-width:760px){.header-inner{padding:15px 18px 0}.brand strong{font-size:17px;overflow-wrap:anywhere}.brand>span:last-child{min-width:0}.brand-mark{flex-shrink:0}.main-shell{padding:18px 14px 38px}nav{overflow:auto;justify-content:flex-start}nav button{white-space:nowrap;padding:0 12px}}
</style>
