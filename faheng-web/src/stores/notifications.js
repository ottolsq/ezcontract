import { defineStore } from 'pinia'
import api from '../api'

export const useNotificationsStore = defineStore('notifications', {
  state: () => ({
    items: [],
    unread: 0,
    timer: null,
    knownIds: [], // 已见过的通知 id，用于新通知弹提示
  }),

  actions: {
    startPolling() {
      if (this.timer) return
      this.fetch()
      this.timer = setInterval(() => this.fetch(), 60000)
    },

    stopPolling() {
      clearInterval(this.timer)
      this.timer = null
    },

    async fetch() {
      try {
        const { data } = await api.get('/notifications')
        const newIds = data.items.map((n) => n.id).filter((id) => !this.knownIds.includes(id))
        // 首次拉取只记录不弹窗；之后的新通知弹一次
        if (this.knownIds.length && newIds.length) {
          const latest = data.items.find((n) => n.id === newIds[0])
          if (latest) {
            import('element-plus').then(({ ElMessage }) => {
              ElMessage.info(latest.title)
            })
          }
        }
        this.knownIds = data.items.map((n) => n.id)
        this.items = data.items
        this.unread = data.unread
      } catch {
        /* 拦截器已提示；轮询静默继续 */
      }
    },

    async markRead(ids) {
      const { data } = await api.post('/notifications/read', { ids })
      this.unread = data.unread
      await this.fetch()
    },

    async markAllRead() {
      const { data } = await api.post('/notifications/read', { all: true })
      this.unread = data.unread
      await this.fetch()
    },
  },
})
