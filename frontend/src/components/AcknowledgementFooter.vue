<script setup>
defineProps({ publicVersion: Boolean })

const institutions = [
  { name: '湖南科技大学', url: 'https://www.hnust.edu.cn/', title: '访问学校官网（新窗口）' },
  { name: '湖南科技大学计算机科学与工程学院', url: 'https://computer.hnust.edu.cn/', title: '访问学院官网（新窗口）' },
  { name: '服务计算与软件服务新技术湖南省重点实验室' },
]
const teachers = [
  { name: '刘建勋', url: 'https://faculty.hnust.edu.cn/pubtphp/jsjkxygcxy/1050037/chinese/index.html' },
  { name: '王焕宇', url: 'https://faculty.hnust.edu.cn/pubtphp/jsjkxygcxy/1050148/chinese/index.html' },
  { name: '黄晶', url: 'https://faculty.hnust.edu.cn/pubtphp/jsjkxygcxy/1050135/chinese/index.html' },
]
</script>

<template>
  <footer class="acknowledgement-footer" :class="{ 'public-footer': publicVersion }">
    <div class="footer-summary">
      <span>Global CS Paper Awards · 学术资料索引</span>
      <span>{{ publicVersion ? '保留原始奖项与来源 · 数据由本地审核后发布' : '保留原始来源 · 缺失信息标注未知 · 核验状态可追溯' }}</span>
    </div>
    <div class="footer-acknowledgements">
      <span class="acknowledgement-label">致谢</span>
      <ul aria-label="致谢单位">
        <li v-for="institution in institutions" :key="institution.name">
          <a v-if="institution.url" :href="institution.url" :title="institution.title" target="_blank" rel="noopener noreferrer">{{ institution.name }}</a>
          <span v-else>{{ institution.name }}</span>
        </li>
      </ul>
    </div>
    <div class="footer-acknowledgements teacher-acknowledgements">
      <span class="acknowledgement-label">特别致谢</span>
      <ul aria-label="致谢老师的个人介绍">
        <li v-for="teacher in teachers" :key="teacher.name">
          <a :href="teacher.url" :title="`查看${teacher.name}老师的介绍（新窗口）`" target="_blank" rel="noopener noreferrer">{{ teacher.name }}</a>
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
.teacher-acknowledgements{margin-top:8px}
.acknowledgement-label{flex-shrink:0;font-weight:600;color:#45566c}
ul{display:flex;flex-wrap:wrap;gap:8px 24px;padding:0;margin:0;list-style:none}
li{min-width:0}
a{color:#245c96;text-decoration:none;text-underline-offset:3px;overflow-wrap:anywhere}
a:hover{text-decoration:underline;color:#1476d4}
a:focus-visible{outline:3px solid #90b8e6;outline-offset:3px;border-radius:2px}
@media(max-width:760px){.acknowledgement-footer{padding:20px}.footer-summary{flex-direction:column}.footer-acknowledgements{gap:10px}ul{flex-direction:column;gap:6px}}
</style>
