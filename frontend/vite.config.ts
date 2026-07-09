import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // `npm run dev` proxies /api straight to the FastAPI backend (run
    // separately with `uvicorn app.main:app --reload`) so there's no CORS
    // config to maintain -- the browser only ever talks to one origin.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
