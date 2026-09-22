import { defineStore } from 'pinia'
import api from '../api'

const TOKEN_KEY = 'faheng_token'
const USERNAME_KEY = 'faheng_username'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    // 从 localStorage 初始化——刷新页面也保持登录态
    token: localStorage.getItem(TOKEN_KEY) || '',
    username: localStorage.getItem(USERNAME_KEY) || '',
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
      this.token = data.access_token
      this.username = data.username
      localStorage.setItem(TOKEN_KEY, this.token)
      localStorage.setItem(USERNAME_KEY, this.username)
      return data
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
    },
  },
})
