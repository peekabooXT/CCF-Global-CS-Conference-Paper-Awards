<script setup>
defineProps({ publicVersion: Boolean })

const institutions = [
  { name: '湖南科技大学', url: 'https://www.hnust.edu.cn/', title: '访问学校官网（新窗口）' },
  { name: '湖南科技大学计算机科学与工程学院', url: 'https://computer.hnust.edu.cn/', title: '访问学院官网（新窗口）' },
  { name: '服务计算与软件服务新技术湖南省重点实验室', url: 'https://computer.hnust.edu.cn/xyxw/4403db98401440288088d39953e56d4d.htm', title: '查看学院官网的实验室介绍（新窗口）' },
]
</script>

<template>
  <footer class="acknowledgement-footer" :class="{ 'public-footer': publicVersion }">
    <div class="footer-summary">
      <span>Global CS Paper Awards Agent · 学术资料索引</span>
      <span>{{ publicVersion ? '保留原始奖项与来源 · 数据由本地审核后发布' : '保留原始来源 · 缺失信息标注未知 · 核验状态可追溯' }}</span>
    </div>
    <div class="footer-acknowledgements">
      <span class="acknowledgement-label">致谢</span>
      <ul aria-label="致谢单位官方网站与介绍">
        <li v-for="institution in institutions" :key="institution.url">
          <a :href="institution.url" :title="institution.title" target="_blank" rel="noopener noreferrer">{{ institution.name }}</a>
        </li>
      </ul>
    </div>
  </footer>
</template>

<style scoped>
.acknowledgement-footer{width:100%;max-width:1440px;margin:auto;padding:22px 40px;border-top:1px solid #dce4ee;color:#64748b;font-size:12px;line-height:1.8}
.public-footer{max-width:1600px;padding-inline:38px}
.footer-summary{display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px 16px}
.footer-acknowledgements{display:flex;align-items:baseline;gap:14px;margin-top:14px}
.acknowledgement-label{flex-shrink:0;font-weight:600;color:#45566c}
ul{display:flex;flex-wrap:wrap;gap:8px 24px;padding:0;margin:0;list-style:none}
li{min-width:0}
a{color:#245c96;text-decoration:none;text-underline-offset:3px;overflow-wrap:anywhere}
a:hover{text-decoration:underline;color:#1476d4}
a:focus-visible{outline:3px solid #90b8e6;outline-offset:3px;border-radius:2px}
@media(max-width:760px){.acknowledgement-footer{padding:20px}.footer-summary{flex-direction:column}.footer-acknowledgements{gap:10px}ul{flex-direction:column;gap:6px}}
</style>
