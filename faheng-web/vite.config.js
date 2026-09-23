import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 58068,
    host: true,
    proxy: {
      '/api': 'http://localhost:58069',
    },
  },
})
