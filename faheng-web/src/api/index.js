import axios from 'axios'
import { ElMessage } from 'element-plus'

const TOKEN_KEY = 'faheng_token'

const api = axios.create({ baseURL: '/api', timeout: 300000 })

// 请求拦截：自动带 Bearer token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status
    const msg = err.response?.data?.detail || err.message || '请求失败'
    // 登录接口的 401 = 账号或密码错误，先提示再让调用方决定跳转
    const isLoginRequest = err.config?.url?.endsWith('/auth/login')
    if (status === 401 && !isLoginRequest) {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem('faheng_username')
      if (!location.pathname.startsWith('/login')) {
        location.href = '/login'
      }
    } else if (status === 401 && isLoginRequest) {
      ElMessage.error(String(msg))
    } else if (status) {
      ElMessage.error(String(msg))
    }
    return Promise.reject(err)
  },
)

/**
 * 触发浏览器下载（blob → a 标签）
 * @param {string} url
 * @param {string} filename
 * @param {object|null} [data] 可选请求体（如导出时携带 TipTap HTML）
 */
export async function download(url, filename, data = null) {
  const res = await api.post(url, data, { responseType: 'blob' })
  const blob = new Blob([res.data])
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(link.href)
}

export default api
