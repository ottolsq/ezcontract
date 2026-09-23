import { defineStore } from 'pinia'
import api from '../api'
import { bestMatchSegments, spliceReplacedSegments } from './review-diff'

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
    // 条款原始内容备份（采纳/撤销时用于把条款还原回原始合同，并防止多决策叠加）
    originalClauses: {},
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
      this._snapshotOriginalClauses()
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
      this._snapshotOriginalClauses()
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
      this._snapshotOriginalClauses()
      // 默认选中第一个可见风险
      this.filters.level = this.stats.high > 0 ? 'high' : 'medium'
      this.filters.status = 'pending'
      this.currentRiskId = this.visibleRisks[0]?.risk_id || ''
      this.phase = 'workspace'
    },

    /** 把当前 clauses 备份为原始版本（采纳/撤销都基于此重建） */
    _snapshotOriginalClauses() {
      this.originalClauses = Object.fromEntries(
        this.clauses.map((c) => [c.clause_id, { html: c.html, text: c.text }]),
      )
    },

    /** 把某条款下所有 accepted/modified 决策依次套用到原始内容上，得到最新 html/text */
    _rebuildClauseHtml(clauseId) {
      const original = this.originalClauses[clauseId]
      const idx = this.clauses.findIndex((c) => c.clause_id === clauseId)
      if (!original || idx < 0) return

      const decisionsForClause = Object.values(this.decisions)
        .filter((d) => {
          const risk = this.risks.find((r) => r.risk_id === d.risk_id)
          return (
            risk &&
            risk.clause_id === clauseId &&
            (d.type === 'accepted' || d.type === 'modified')
          )
        })
        // 按风险在清单中的原始顺序应用，保证多次决策结果稳定
        .sort((a, b) => {
          const ia = this.risks.findIndex((r) => r.risk_id === a.risk_id)
          const ib = this.risks.findIndex((r) => r.risk_id === b.risk_id)
          return ia - ib
        })

      let html = original.html
      let text = original.text
      for (const d of decisionsForClause) {
        const finalText = (d.text || '').trim()
        if (!finalText) continue
        const segments = finalText
          .split(/\r?\n/)
          .map((s) => s.trim())
          .filter(Boolean)
        const matches = bestMatchSegments(text, segments)
        html = spliceReplacedSegments(html, matches)
        // text 同步替换，便于下一轮决策继续在最新文本上做相似度匹配
        text = segments.join('\n')
      }

      this.clauses = [
        ...this.clauses.slice(0, idx),
        { ...this.clauses[idx], html, text },
        ...this.clauses.slice(idx + 1),
      ]
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
      // 基于原始内容重新应用该条款所有决策（防止叠加漂移）
      this._rebuildClauseHtml(risk.clause_id)
      // 跳到下一条待处理
      const next = this.visibleRisks.find((r) => r.risk_id !== risk.risk_id)
      if (next) this.currentRiskId = next.risk_id
      await api.put(`/review/${this.reviewId}/decisions`, {
        decisions: Object.values(this.decisions),
      })
    },

    async undoDecision(risk) {
      const clauseId = risk.clause_id
      const d = { ...this.decisions }
      delete d[risk.risk_id]
      this.decisions = d
      this.currentRiskId = risk.risk_id
      // 用原始内容重建该条款：撤销后无剩余决策时还原为原始合同文本
      this._rebuildClauseHtml(clauseId)
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
