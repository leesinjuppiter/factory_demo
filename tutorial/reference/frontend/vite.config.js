import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: { rollupOptions: { input: { display: 'index.html', admin: 'admin.html' } } },
  server: { port: 5176, proxy: { '/api': { target: 'http://127.0.0.1:8876', ws: true } } },
})
