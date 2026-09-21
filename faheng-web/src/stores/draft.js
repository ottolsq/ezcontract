import { defineStore } from 'pinia'
import api from '../api'

export const useDraftStore = defineStore('draft', {
  state: () => ({
    draftId: '',
    title: '',
    markdown: '',
    keywords: '',
    history: [],
    loading: false,
    revising: false,
    saved: true, // 防抖保存标记
  }),

  actions: {
    async generate(form) {
      this.loading = true
      try {
        const { data } = await api.post('/draft/generate', form)
        this.draftId = data.id
        this.title = data.title
        this.markdown = data.markdown
        this.keywords = form.keywords
        this.history = data.history || []
      } finally {
        this.loading = false
      }
    },

    async revise(instruction) {
      this.revising = true
      try {
        const { data } = await api.post(`/draft/${this.draftId}/revise`, {
          instruction,
        })
        this.title = data.title
        this.markdown = data.markdown
        this.history = data.history || []
      } finally {
        this.revising = false
      }
    },

    /** 在线编辑防抖保存 */
    updateContent(markdown) {
      this.markdown = markdown
      this.saved = false
      clearTimeout(this._saveTimer)
      this._saveTimer = setTimeout(async () => {
        await api.put(`/draft/${this.draftId}/content`, { markdown })
        this.saved = true
      }, 800)
    },
  },
})
