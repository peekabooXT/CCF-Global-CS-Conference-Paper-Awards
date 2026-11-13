<script setup>
import { t } from '../i18n.js'
defineProps({ title: String, description: String, meta: Object })
</script>

<template>
  <header class="paper-page-heading">
    <div class="page-heading-copy">
      <div class="eyebrow">CCF GLOBAL CS CONFERENCE BEST PAPER AWARDS</div>
      <h1>{{ t(title) }}</h1>
      <p>{{ t(description) }}</p>
    </div>
    <p v-if="meta?.mode === 'public'" class="page-publication">
      <span>{{ t("最近发布：") }}{{ meta.publication?.published_at || t('尚未发布') }}</span>
      <span class="publication-label">{{ t("已核验公开数据") }}</span>
    </p>
  </header>
</template>

<style scoped>
.paper-page-heading{display:flex;justify-content:space-between;align-items:center;gap:20px 32px;margin-bottom:24px}
.page-heading-copy{min-width:0}.eyebrow{font-size:11px;font-weight:750;letter-spacing:.14em;color:#2780df}
h1{font-size:30px;line-height:1.2;letter-spacing:-.02em;color:#102f59;margin:8px 0 9px}
.page-heading-copy p{font-size:14px;color:#70839b;margin:0;line-height:1.6}
.page-publication{flex-shrink:0;display:flex;flex-direction:column;align-items:flex-end;gap:5px;font-size:12px;color:#70839b;margin:0;line-height:1.6}
.publication-label{font-size:11px;color:#4f7997;background:#edf5fc;border:1px solid #dce8f5;border-radius:5px;padding:2px 8px}
@media(max-width:1050px){.paper-page-heading{align-items:flex-start;flex-wrap:wrap;gap:12px}.page-publication{align-items:flex-start;flex-direction:row;flex-wrap:wrap;align-items:center;gap:6px 12px}}
@media(max-width:760px){h1{font-size:26px}.paper-page-heading{margin-bottom:20px}.page-publication{flex-shrink:1;overflow-wrap:anywhere}}
</style>
