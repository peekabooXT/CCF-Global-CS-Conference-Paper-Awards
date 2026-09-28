import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // 前端 /api/* 转发到本地 FastAPI（api.py）
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
