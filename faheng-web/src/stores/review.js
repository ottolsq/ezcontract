import { defineStore } from 'pinia'
import api from '../api'
import {
  bestMatchSegments,
  spliceReplacedSegments,
  replaceParagraphText,
  SUBITEM_RE,
} from './review-diff'

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
    /**
     * 当前剩余风险分：仅采纳(accepted)/修改(modified)算"已消除"，驳回(rejected)维持。
     * 权重与后端保持一致（15 / 7，最高 100）。
     */
    liveScore: (s) => {
      const eliminated = new Set(
        Object.values(s.decisions)
          .filter((d) => d && (d.type === 'accepted' || d.type === 'modified'))
          .map((d) => d.risk_id),
      )
      let high = 0
      let medium = 0
      for (const r of s.risks) {
        if (eliminated.has(r.risk_id)) continue
        if (r.level === 'high') high += 1
        else if (r.level === 'medium') medium += 1
      }
      return Math.min(100, high * 15 + medium * 7)
    },
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
      // score 已由前端 liveScore 派生，不再使用后端返回值
      this.score = 0
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

    /** 把 finalText 头部补上 subNo 编号前缀（若原行以 X.Y 开头而 finalText 没有） */
    _ensureSubItemNoForText(originalText, finalText) {
      const orig = (originalText || '').trim()
      const text = (finalText || '').replace(/^\s+/, '')
      const origMatch = SUBITEM_RE.exec(orig)
      const newMatch = SUBITEM_RE.exec(text)
      if (!origMatch) return text
      if (newMatch) return text
      return `${origMatch[0]}${text}`
    },

    /** 按行替换原 text 中的目标行，返回新的 text。
     * - 若 subNo 非空，定位原 text 中以该编号开头的行替换；
     * - 若 finalText 不带原编号，自动把原编号前缀补回去；
     * - 若无 subNo 且 finalText 是单段带 X.Y，回退到按该 X.Y 处理；
     * - 其它情况按段数对齐原行替换。
     */
    _applyLineReplace(originalText, subNo, finalText) {
      const lines = originalText
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean)
      const newLines = finalText
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean)
      if (!lines.length) return newLines.join('\n')

      // 命中子项编号 → 替换原 text 中以该编号开头的行
      if (subNo) {
        const re = new RegExp(`^${subNo.replace(/\./g, '\\.')}[\\s　:：、]`)
        let replaced = false
        const out = lines.map((ln) => {
          if (!replaced && re.test(ln)) {
            replaced = true
            return this._ensureSubItemNoForText(ln, finalText)
          }
          return ln
        })
        if (replaced) return out.join('\n')
        // 没找到原行 → 追加（也补编号）
        out.push(this._ensureSubItemNoForText('', finalText))
        return out.join('\n')
      }

      // 无 subNo 且 finalText 单段：尝试从前缀抓 X.Y 编号
      if (newLines.length === 1) {
        const m = SUBITEM_RE.exec(newLines[0])
        if (m) return this._applyLineReplace(originalText, m[1], newLines[0])
      }

      // 兜底：多段 finalText 按段数对齐原行（保留行结构，避免整段覆盖）
      const out = [...lines]
      for (let i = 0; i < newLines.length && i < out.length; i++) {
        out[i] = newLines[i]
      }
      return out.join('\n')
    },

    /** 把某条款下所有 accepted/modified 决策依次套用到原始内容上，得到最新 html/text */
    _rebuildClauseHtml(clauseId) {
      const original = this.originalClauses[clauseId]
      const idx = this.clauses.findIndex((c) => c.clause_id === clauseId)
      if (!original || idx < 0) return

      const clause = this.clauses[idx]

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
        const risk = this.risks.find((r) => r.risk_id === d.risk_id)
        const subNo = d.sub_item_no || risk?.sub_item_no || ''
        if (subNo) {
          // 精确按子项编号替换：保留原 <p> 开标签 + 样式
          html = replaceParagraphText(html, subNo, finalText)
        } else {
          // 兜底：Jaccard 多段匹配（保留旧实现以兼容整条款风险）
          const segments = finalText
            .split(/\r?\n/)
            .map((s) => s.trim())
            .filter(Boolean)
          const matches = bestMatchSegments(text, segments)
          html = spliceReplacedSegments(html, matches)
        }
        // text 按行替换：仅替换以 subNo 开头的行，避免整条款 text 被覆盖
        text = this._applyLineReplace(text, subNo, finalText)
      }

      this.clauses = [
        ...this.clauses.slice(0, idx),
        { ...clause, html, text },
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
        sub_item_no: payload.sub_item_no ?? risk.sub_item_no ?? null,
      }
      this.decisions = { ...this.decisions, [risk.risk_id]: decision }
      // 基于原始内容重新应用该条款所有决策（防止叠加漂移）
      this._rebuildClauseHtml(risk.clause_id)
      // 保持当前选中不跳转，便于用户在正文中直接确认绿色修改框
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
