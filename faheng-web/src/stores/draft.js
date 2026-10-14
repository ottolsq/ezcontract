import { defineStore } from 'pinia'
import api from '../api'
import { ElMessage } from 'element-plus'

const DRAFT_SESSION_KEY = 'faheng_draft_session'

function _loadSession() {
  try {
    const raw = localStorage.getItem(DRAFT_SESSION_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function _saveSession(session) {
  try {
    if (session) {
      localStorage.setItem(DRAFT_SESSION_KEY, JSON.stringify(session))
    } else {
      localStorage.removeItem(DRAFT_SESSION_KEY)
    }
  } catch {
    // 隐私模式等场景忽略
  }
}

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
    // 轮询相关
    pollingTimer: null,
    status: '', // idle / processing / completed / failed
    progress: 0,
    stage: '',
    error: '',
  }),

  actions: {
    async generate(form) {
      this.reset()
      this.loading = true
      this.status = 'processing'
      this.progress = 10
      this.stage = '正在提交生成请求'
      this.keywords = form.keywords
      try {
        const { data } = await api.post('/draft/generate', form)
        this._hydrateFromSession(data)
        // 拿到 draftId 后立即持久化，刷新后才能恢复任务
        this._persistSession()
        if (data.status === 'completed') {
          ElMessage.success('合同模板生成完成')
        } else if (data.status === 'failed') {
          this.error = data.error || '合同生成失败'
          ElMessage.error(this.error)
        } else {
          // 后端仍在处理，开始轮询
          this.poll()
        }
      } catch (error) {
        // 初始请求失败时停止 loading 状态，让用户可重新提交
        this.reset()
      } finally {
        this.loading = false
      }
    },

    async revise(instruction) {
      if (!this.draftId) return
      this.revising = true
      this.status = 'processing'
      this.progress = 10
      this.stage = '正在提交修订请求'
      this._persistSession()
      try {
        const { data } = await api.post(`/draft/${this.draftId}/revise`, {
          instruction,
        })
        this._hydrateFromSession(data)
        if (data.status === 'completed') {
          ElMessage.success('合同修订完成')
        } else if (data.status === 'failed') {
          this.error = data.error || '合同修订失败'
          ElMessage.error(this.error)
        } else {
          this.poll()
        }
      } catch (error) {
        // 请求失败后恢复到编辑态，避免卡在 processing
        this.status = 'failed'
        this.progress = 0
        this.stage = ''
      } finally {
        this.revising = false
      }
    },

    poll() {
      clearTimeout(this.pollingTimer)
      if (!this.draftId) return
      this.pollingTimer = setTimeout(async () => {
        try {
          const { data } = await api.get(`/draft/${this.draftId}/status`)
          this.status = data.status
          this.progress = data.progress
          this.stage = data.stage
          if (data.status === 'processing') {
            this.poll()
          } else if (data.status === 'completed') {
            await this.fetchDraft()
          } else if (data.status === 'failed') {
            this.error = data.error || '任务失败'
            ElMessage.error(this.error)
          }
        } catch {
          // 网络抖动继续轮询
          this.poll()
        }
      }, 1500)
    },

    async fetchDraft() {
      if (!this.draftId) return
      const { data } = await api.get(`/draft/${this.draftId}`)
      this._hydrateFromSession(data)
      if (data.status === 'completed') {
        this._persistSession()
      }
    },

    /** 从后端 session 数据同步到 store */
    _hydrateFromSession(data) {
      this.draftId = data.id || this.draftId
      this.title = data.title || ''
      this.markdown = data.markdown || ''
      this.keywords = data.keywords || this.keywords
      this.history = data.history || []
      this.status = data.status || 'idle'
      this.progress = data.progress ?? 0
      this.stage = data.stage || ''
      this.error = data.error || ''
      this.loading = this.status === 'processing' && !this.title
      this.revising = this.status === 'processing' && Boolean(this.title)
    },

    _persistSession() {
      _saveSession({
        draftId: this.draftId,
        phase: this.status === 'completed' ? 'editor' : 'processing',
        status: this.status,
        title: this.title,
        keywords: this.keywords,
      })
    },

    /** 页面刷新后尝试恢复未完成的起草任务 */
    async restoreSession() {
      const session = _loadSession()
      if (!session?.draftId) return
      if (this.draftId && this.draftId !== session.draftId) {
        _saveSession(null)
        return
      }
      this.draftId = session.draftId
      this.title = session.title || ''
      this.keywords = session.keywords || ''
      try {
        const { data } = await api.get(`/draft/${this.draftId}/status`)
        this.status = data.status
        this.progress = data.progress
        this.stage = data.stage
        if (data.status === 'processing') {
          this.loading = true
          this.revising = Boolean(this.title)
          this.poll()
        } else if (data.status === 'completed') {
          await this.fetchDraft()
        } else if (data.status === 'failed') {
          this.error = data.error || '任务失败'
          this.loading = false
          this.revising = false
        } else {
          this.status = 'idle'
          this.loading = false
          this.revising = false
        }
      } catch (err) {
        const status = err.response?.status
        if (status === 404) {
          ElMessage.warning('之前的起草任务已过期，请重新创建')
        } else {
          ElMessage.error('恢复起草任务失败，请刷新重试')
        }
        this.reset()
      }
    },

    async cancel() {
      if (!this.draftId) return
      try {
        await api.post(`/draft/${this.draftId}/cancel`)
        ElMessage.info('已取消任务')
      } catch {
        // 即使后端报错也清空本地
      }
      this.reset()
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

    reset() {
      clearTimeout(this.pollingTimer)
      _saveSession(null)
      this.$reset()
    },
  },
})
