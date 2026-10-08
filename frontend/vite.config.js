import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'

export default defineConfig(({ mode }) => ({
  define: { 'import.meta.env.VITE_APP_MODE': JSON.stringify(mode === 'public' ? 'public' : 'local') },
  build: { target: 'esnext' },
  plugins: [vue(), {
    name: 'public-api-only',
    enforce: 'pre',
    resolveId(source) {
      if (mode === 'public' && /^(\.\/|\.\.\/)api\.js$/.test(source))
        return fileURLToPath(new URL('./src/public-api.js', import.meta.url))
    },
  }],
  server: {
    port: 5173,
    proxy: {
      // 前端 /api/* 转发到本地 FastAPI（api.py）
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
}))
