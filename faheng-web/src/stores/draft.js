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

    /**
     * 导出 Word。
     * @param {string} title 文件名（不含扩展名）
     * @param {string} [html] 当前 TipTap 的 HTML；传入则走 HTML 高保真导出
     */
    async exportDocx(title, html) {
      const safeTitle = (title || '合同草稿').slice(0, 30)
      const payload = html && html.trim() ? { html } : null
      const { download } = await import('../api')
      await download(`/draft/${this.draftId}/export`, `${safeTitle}.docx`, payload)
    },
  },
})
