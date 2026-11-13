<script setup>
import { t, locale } from '../i18n.js'
import universityLogo from '../assets/hnust.svg'
import collegeLogo from '../assets/hnust-computer.png'
defineProps({ publicVersion: Boolean })

const institutions = [
  { logo: universityLogo, logoClass: 'university-mark', width: 210, height: 49, name: '湖南科技大学', url: 'https://www.hnust.edu.cn/', title: '访问学校官网（新窗口）' },
  { logo: collegeLogo, logoClass: 'college-mark', width: 788, height: 84, name: '湖南科技大学计算机科学与工程学院', url: 'https://computer.hnust.edu.cn/', title: '访问学院官网（新窗口）' },
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
      <span>{{ t("CCF Global CS Conference Best Paper Awards · 学术资料索引") }}</span>
      <span>{{ publicVersion ? t('保留原始奖项与来源 · 数据由本地审核后发布') : t('保留原始来源 · 缺失信息标注未知 · 核验状态可追溯') }}</span>
    </div>
    <div class="footer-acknowledgements institution-acknowledgements">
      <span class="acknowledgement-label">{{ t("致谢") }}</span>
      <ul class="institution-list" :aria-label="t(&quot;致谢单位&quot;)">
        <li v-for="institution in institutions" :key="institution.name" :class="{ 'institution-logo-item': institution.logo }">
          <a v-if="institution.url" :href="institution.url" :title="t(institution.title)" :class="institution.logoClass" target="_blank" rel="noopener noreferrer">
            <img v-if="institution.logo" :src="institution.logo" :alt="t(institution.name)" :width="institution.width" :height="institution.height" />
            <template v-else>{{ t(institution.name) }}</template>
          </a>
          <span v-else class="laboratory-mark" :class="{ 'is-english': locale === 'en' }" :aria-label="t(institution.name)">
            <strong>{{ locale === 'zh' ? '服务计算与软件服务新技术' : 'Service Computing & Novel Software Service Technologies' }}</strong>
            <small>{{ locale === 'zh' ? '湖南省重点实验室' : 'Hunan Provincial Key Laboratory' }}</small>
          </span>
        </li>
      </ul>
    </div>
    <div class="footer-acknowledgements teacher-acknowledgements">
      <span class="acknowledgement-label">{{ t("特别致谢") }}</span>
      <ul :aria-label="t(&quot;致谢老师的个人介绍&quot;)">
        <li v-for="teacher in teachers" :key="teacher.name">
          <a :href="teacher.url" :title="t(`查看${teacher.name}老师的介绍（新窗口）`)" target="_blank" rel="noopener noreferrer">{{ t(teacher.name) }}</a>
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
.institution-acknowledgements{align-items:flex-start;margin-top:20px}
.institution-acknowledgements>.acknowledgement-label{padding-top:17px}
.institution-list{align-items:center;gap:16px 22px;min-width:0;flex:1}
.institution-logo-item{max-width:100%}
.institution-list>li:last-child{flex-basis:auto}
.university-mark{display:flex;align-items:center;min-height:58px}
.university-mark img{display:block;width:190px;height:auto;max-width:100%}
.college-mark{display:flex;align-items:center;width:418px;max-width:100%;padding:10px 12px;background:#123d70;border-radius:8px}
.college-mark img{display:block;width:100%;height:auto;object-fit:contain}
.laboratory-mark{display:flex;flex-direction:column;justify-content:center;gap:3px;width:clamp(260px,23vw,340px);max-width:100%;min-height:62px;padding:9px 16px;border-radius:8px;background:#123d70;color:#fff;font-family:"Segoe UI","Microsoft YaHei",sans-serif;text-align:center}
.laboratory-mark strong{font-size:18px;font-weight:500;line-height:1.4}
.laboratory-mark small{font-size:13px;line-height:1.4;letter-spacing:.1em;color:#e5eef9}
.laboratory-mark.is-english{padding:6px 12px;gap:2px}.laboratory-mark.is-english strong{font-size:15px;line-height:1.25}
.laboratory-mark.is-english small{font-size:11px;line-height:1.25;letter-spacing:.02em}
@media(max-width:760px){.acknowledgement-footer{padding:20px}.footer-summary{flex-direction:column}.footer-acknowledgements{gap:10px}ul{flex-direction:column;gap:6px}.institution-list{align-items:flex-start;gap:12px}.institution-list>li:last-child{flex-basis:auto}.institution-logo-item{width:100%}.college-mark,.laboratory-mark{width:min(418px,100%)}.institution-acknowledgements>.acknowledgement-label{padding-top:16px}}
</style>
