<script setup>
import { locale, setLocale } from '../i18n.js'
</script>
<template>
  <div class="language-switcher" role="group" aria-label="语言 / Language">
    <button lang="zh-CN" :class="{selected:locale==='zh'}" :aria-pressed="locale==='zh'" @click="setLocale('zh')">中文</button>
    <span aria-hidden="true">|</span>
    <button lang="en" :class="{selected:locale==='en'}" :aria-pressed="locale==='en'" @click="setLocale('en')">English</button>
  </div>
</template>
<style scoped>
.language-switcher{display:flex;align-items:center;justify-content:flex-end;gap:10px;flex-shrink:0;padding-top:6px;color:#9aabc0;font-size:13px}
button{border:0;background:none;padding:5px 0;color:#637b98;font:inherit;cursor:pointer}
button.selected{color:#164d85;font-weight:700}button:hover{color:#1476d4}
button:focus-visible{outline:2px solid #90b8e6;outline-offset:4px;border-radius:3px}
</style>
