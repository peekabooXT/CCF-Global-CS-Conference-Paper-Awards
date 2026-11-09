<script setup>
import { t } from '../i18n.js'
import LanguageSwitcher from './LanguageSwitcher.vue'
import { Reading } from '@element-plus/icons-vue'

defineEmits(['home'])
</script>

<template>
  <div class="site-branding">
    <a class="project-brand" href="#" :aria-label="t(&quot;CCF Global CS Conference Paper Awards 首页&quot;)" @click.prevent="$emit('home')">
      <span class="project-mark" aria-hidden="true"><el-icon :size="27"><Reading /></el-icon></span>
      <span class="project-name">
        <strong>CCF Global CS Conference Paper Awards</strong>
        <small>{{ t("中国计算机学会A/B类会议最佳论文获奖资料库") }}</small>
      </span>
    </a>
    <LanguageSwitcher />
  </div>
</template>

<style scoped>
.site-branding{display:flex;align-items:flex-start;justify-content:space-between;gap:24px;width:100%;padding:4px 0 20px}
.project-brand{display:flex;align-items:center;gap:14px;min-width:0;text-decoration:none;color:#102f59}
.project-mark{flex:0 0 48px;height:48px;display:grid;place-items:center;border-radius:12px;color:white;background:linear-gradient(135deg,#1584e6,#1054a9)}
.project-name{min-width:0}
.project-name strong{display:block;font-size:clamp(20px,1.8vw,27px);font-weight:700;line-height:1.3;letter-spacing:-.025em}
.project-name small{display:block;margin-top:7px;color:#667f9d;font-size:13px;line-height:1.6;letter-spacing:.04em}
.project-brand:focus-visible{outline:3px solid #90b8e6;outline-offset:5px;border-radius:8px}
@media(max-width:600px){.site-branding{flex-wrap:wrap;gap:8px;padding-bottom:18px}.project-brand{align-items:flex-start;gap:10px}.project-mark{flex-basis:40px;height:40px;border-radius:10px}.project-name strong{font-size:19px;line-height:1.35;letter-spacing:-.02em}.project-name small{font-size:11px;letter-spacing:0;margin-top:5px}}
.site-branding>:last-child{margin-left:auto}
</style>
