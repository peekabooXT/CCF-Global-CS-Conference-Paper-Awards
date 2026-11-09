import { createApp, h } from 'vue'
import ElementPlus, { ElConfigProvider } from 'element-plus'
import en from 'element-plus/es/locale/lang/en'
import { locale } from './i18n.js'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import './layout.css'
import App from './App.vue'

createApp({ setup: () => () => h(ElConfigProvider, { locale: locale.value === 'en' ? en : zhCn }, () => h(App)) }).use(ElementPlus).mount('#app')
