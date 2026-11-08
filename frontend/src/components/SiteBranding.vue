<script setup>
import { Reading } from '@element-plus/icons-vue'
import universityLogo from '../assets/hnust.svg'
import collegeLogo from '../assets/hnust-computer.png'

defineEmits(['home'])
</script>

<template>
  <div class="site-branding">
    <a class="project-brand" href="#" aria-label="CCF Global CS Conference Paper Awards 首页" @click.prevent="$emit('home')">
      <span class="project-mark" aria-hidden="true"><el-icon :size="27"><Reading /></el-icon></span>
      <span class="project-name">
        <strong>CCF Global CS Conference Paper Awards</strong>
        <small>中国计算机学会A/B类会议最佳论文获奖资料库</small>
      </span>
    </a>
    <div class="institution-branding" aria-label="学校与学院">
      <a class="university-brand" href="https://www.hnust.edu.cn/" target="_blank" rel="noopener noreferrer" title="湖南科技大学（新窗口）">
        <img :src="universityLogo" alt="湖南科技大学" width="210" height="49" />
      </a>
      <a class="college-brand" href="https://computer.hnust.edu.cn/" target="_blank" rel="noopener noreferrer" title="湖南科技大学计算机科学与工程学院（新窗口）">
        <span class="college-wordmark"><img :src="collegeLogo" alt="湖南科技大学计算机科学与工程学院" width="394" height="42" /></span>
        <span class="college-caption" aria-hidden="true">湖南科技大学 · 计算机科学与工程学院</span>
      </a>
    </div>
  </div>
</template>

<style scoped>
.site-branding{display:flex;align-items:center;justify-content:space-between;gap:24px;width:100%;padding:4px 0 20px}
.project-brand{display:flex;align-items:center;gap:14px;min-width:0;text-decoration:none;color:#102f59}
.project-mark{flex:0 0 48px;height:48px;display:grid;place-items:center;border-radius:12px;color:white;background:linear-gradient(135deg,#1584e6,#1054a9)}
.project-name{min-width:0}
.project-name strong{display:block;font-size:clamp(20px,1.8vw,27px);font-weight:700;line-height:1.3;letter-spacing:-.025em}
.project-name small{display:block;margin-top:7px;color:#667f9d;font-size:13px;line-height:1.6;letter-spacing:.04em}
.institution-branding{display:flex;align-items:center;gap:20px;flex-shrink:0}
.university-brand{display:flex;align-items:center}
.university-brand img{display:block;width:184px;height:auto}
.college-brand{display:flex;flex-direction:column;align-items:center;justify-content:center;width:222px;min-height:64px;padding:5px 10px 7px;background:#123d70;border-radius:8px;text-decoration:none}
/* The official college header includes the university lockup at the left.
   Show its college wordmark here beside the separate official university logo. */
.college-wordmark{display:block;position:relative;width:200px;height:31px;overflow:hidden}
.college-wordmark img{position:absolute;right:0;top:0;display:block;width:394px;height:42px;max-width:none}
.college-caption{color:#dce9f8;font-size:9px;line-height:1.5;letter-spacing:.05em;white-space:nowrap}
.project-brand:focus-visible,.institution-branding a:focus-visible{outline:3px solid #90b8e6;outline-offset:5px;border-radius:8px}
@media(max-width:1200px){.site-branding{flex-wrap:wrap;gap:18px}.institution-branding{margin-left:62px}.project-name strong{font-size:24px}}
@media(max-width:600px){.site-branding{gap:18px;padding-bottom:18px}.project-brand{align-items:flex-start;gap:10px}.project-mark{flex-basis:40px;height:40px;border-radius:10px}.project-name strong{font-size:19px;line-height:1.35;letter-spacing:-.02em}.project-name small{font-size:11px;letter-spacing:0;margin-top:5px}.institution-branding{width:100%;margin-left:0;gap:14px;justify-content:flex-start;flex-wrap:wrap}.university-brand img{width:140px}.college-brand{width:182px;min-height:52px;padding:3px 8px 5px}.college-wordmark{width:164px;height:26px}.college-wordmark img{width:323px;height:34.4px}.college-caption{font-size:8px;letter-spacing:0}}
</style>
