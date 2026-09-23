import { defineStore } from 'pinia'
import api from '../api'

export const useReviewStore = defineStore('review', {
  state: () => ({
    // 视图状态机：upload → uploaded → processing → workspace → report
    phase: 'upload',
    reviewId: '',
    filename: '',
    fileType: '',
    clauses: [],
    preambleHtml: '',
    tailHtml: '',
    risks: [],
    decisions: {}, // risk_id -> { type, text, reason }
    score: 0,
    currentRiskId: '',
    filters: { level: 'high', status: 'pending' },
    progress: { percent: 0, stage: '' },
    status: '', // uploaded/processing/completed/failed
    error: '',
    pollingTimer: null,
    truncatedSalvaged: false,
  }),

  getters: {
    stats: (s) => ({
      high: s.risks.filter((r) => r.level === 'high').length,
      medium: s.risks.filter((r) => r.level === 'medium').length,
      low: s.risks.filter((r) => r.level === 'low').length,
    }),
    processedCount: (s) => Object.keys(s.decisions).length,
    currentRisk: (s) => s.risks.find((r) => r.risk_id === s.currentRiskId) || null,
    visibleRisks(s) {
      return s.risks.filter((r) => {
        const levelOk = r.level === s.filters.level
        const decided = Boolean(s.decisions[r.risk_id])
        const statusOk = s.filters.status === 'processed' ? decided : !decided
        return levelOk && statusOk
      })
    },
    clauseMap: (s) => Object.fromEntries(s.clauses.map((c) => [c.clause_id, c])),
  },

  actions: {
    async uploadFile(file) {
      const fd = new FormData()
      fd.append('file', file)
      const { data } = await api.post('/review/upload', fd)
      this.reset()
      this.reviewId = data.review_id
      this.filename = data.filename
      this.fileType = data.file_type
      this.clauses = data.clauses
      this.preambleHtml = data.preamble_html || ''
      this.tailHtml = data.tail_html || ''
      this.phase = 'uploaded'
    },

    async loadSample() {
      const { data } = await api.post('/review/sample')
      this.reset()
      this.reviewId = data.review_id
      this.filename = data.filename
      this.fileType = data.file_type
      this.clauses = data.clauses
      this.preambleHtml = data.preamble_html || ''
      this.tailHtml = data.tail_html || ''
      this.phase = 'uploaded'
    },

    async startReview() {
      await api.post(`/review/${this.reviewId}/start`)
      this.phase = 'processing'
      this.status = 'processing'
      this.progress = { percent: 0, stage: '正在准备条款审查' }
      this.poll()
    },

    poll() {
      clearTimeout(this.pollingTimer)
      this.pollingTimer = setTimeout(async () => {
        try {
          const { data } = await api.get(`/review/${this.reviewId}/status`)
          this.progress = { percent: data.progress, stage: data.stage }
          this.status = data.status
          if (data.status === 'processing') {
            this.poll()
          } else if (data.status === 'completed') {
            await this.fetchResult()
          } else if (data.status === 'failed') {
            this.error = data.error || '审查失败'
            ElMessage && null
          }
        } catch {
          this.poll() // 网络抖动继续轮询
        }
      }, 1500)
    },

    async fetchResult() {
      const { data } = await api.get(`/review/${this.reviewId}/result`)
      this.risks = data.risks
      this.score = data.score
      this.decisions = data.decisions || {}
      this.truncatedSalvaged = data.truncated_salvaged
      // 服务端可能刷新内存（重载场景），同步一次最新的条款/前后页
      if (data.clauses) this.clauses = data.clauses
      if (data.preamble_html != null) this.preambleHtml = data.preamble_html
      if (data.tail_html != null) this.tailHtml = data.tail_html
      // 默认选中第一个可见风险
      this.filters.level = this.stats.high > 0 ? 'high' : 'medium'
      this.filters.status = 'pending'
      this.currentRiskId = this.visibleRisks[0]?.risk_id || ''
      this.phase = 'workspace'
    },

    /** 决策：本地乐观更新 + 后端保存 */
    async saveDecision(risk, type, payload = {}) {
      const decision = {
        risk_id: risk.risk_id,
        type,
        text: payload.text ?? (type === 'accepted' ? risk.suggestion : null),
        reason: payload.reason ?? null,
      }
      this.decisions = { ...this.decisions, [risk.risk_id]: decision }
      // 跳到下一条待处理
      const next = this.visibleRisks.find((r) => r.risk_id !== risk.risk_id)
      if (next) this.currentRiskId = next.risk_id
      await api.put(`/review/${this.reviewId}/decisions`, {
        decisions: Object.values(this.decisions),
      })
    },

    async undoDecision(risk) {
      const d = { ...this.decisions }
      delete d[risk.risk_id]
      this.decisions = d
      this.currentRiskId = risk.risk_id
      await api.put(`/review/${this.reviewId}/decisions`, {
        decisions: Object.values(this.decisions),
      })
    },

    reset() {
      clearTimeout(this.pollingTimer)
      this.$reset()
    },
  },
})
