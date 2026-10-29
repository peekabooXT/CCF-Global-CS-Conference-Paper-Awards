import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  define: { 'import.meta.env.VITE_APP_MODE': JSON.stringify('public') },
  build: { target: 'esnext' },
  plugins: [vue()],
  server: { host: '127.0.0.1', port: 5173, proxy: { '/api': 'http://127.0.0.1:8000' } },
})
