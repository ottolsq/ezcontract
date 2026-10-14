import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig(({ mode }) => {
  // 从项目根目录加载 .env，与后端共用同一配置文件
  const rootDir = path.resolve(__dirname, '..')
  const env = loadEnv(mode, rootDir, '')
  const apiTarget = env.VITE_API_TARGET || 'localhost:58069'

  return {
    plugins: [vue()],
    envDir: rootDir,
    server: {
      port: 58068,
      host: '0.0.0.0',
      proxy: {
        '/api': apiTarget,
      },
    },
  }
})
