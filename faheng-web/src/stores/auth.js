import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'
import api from '../api'

const TOKEN_KEY = 'faheng_token'
const USERNAME_KEY = 'faheng_username'

/** 清理跨登录会话残留的 localStorage：review/draft 的会话指向后端内存态，
 * 换账号/重新登录后后端 session 已失效，旧 key 只会带出「无法读取」的
 * 死任务。登录与登出都调（需求方确认：只清 localStorage，不动 Pinia
 * 视图态与 SQLite 持久数据）。 */
function clearSessionCache() {
  localStorage.removeItem('faheng_review_session')
  localStorage.removeItem('faheng_draft_session')
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    // 从 localStorage 初始化——刷新页面也保持登录态
    token: localStorage.getItem(TOKEN_KEY) || '',
    username: localStorage.getItem(USERNAME_KEY) || '',
    // LLM 网关健康：登录后查一次（见 checkLlmHealth）；不逐次预检——
    // 预检本身是一次完整 LLM 往返，只会让所有操作延迟翻倍，
    // 真正调用失败时后端 503 提示已覆盖
    llmStatus: '', // '' 未查 | 'ok' | 'error'
    llmError: '',
  }),
  getters: {
    isLoggedIn: (s) => Boolean(s.token),
  },
  actions: {
    /**
     * 登录：POST /api/auth/login → 存 token + username 到 localStorage
     * @param {{ username: string, password: string }} credentials
     */
    async login(credentials) {
      const { data } = await api.post('/auth/login', credentials)
      // 登录即清上一会话的本地缓存（详见 clearSessionCache 注释）
      clearSessionCache()
      this.token = data.access_token
      this.username = data.username
      localStorage.setItem(TOKEN_KEY, this.token)
      localStorage.setItem(USERNAME_KEY, this.username)
      // 登录后查一次 AI 网关健康（不阻塞登录流程，后台跑）
      this.checkLlmHealth()
      return data
    },

    /** 登录后的一次性 AI 网关检查：让用户进系统即知道今天 AI 是否可用，
     * 而不是做到一半才发现。异常时 toast + 存状态（页面可按需展示）。
     * 静默成功——正常时不打扰用户。 */
    async checkLlmHealth() {
      if (!this.isLoggedIn) return
      try {
        const { data } = await api.get('/health', { params: { llm: 1 } })
        this.llmStatus = data.llm || 'ok'
        this.llmError = data.llm_error || ''
        if (this.llmStatus !== 'ok') {
          ElMessage.warning(this.llmError || 'AI 服务暂不可用，请及时联系管理员')
        }
      } catch {
        // 网络级失败：health 接口本身不可达，登录都刚成功了，静默
        this.llmStatus = ''
      }
    },

    /** 退出：通知后端（最佳努力）+ 清本地态 */
    async logout() {
      try {
        await api.post('/auth/logout')
      } catch {
        // 后端可能已重启/网络异常，静默——本地清掉即可
      }
      this.token = ''
      this.username = ''
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USERNAME_KEY)
      clearSessionCache()
    },
  },
})
