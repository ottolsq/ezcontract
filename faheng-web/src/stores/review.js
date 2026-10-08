import { defineStore } from 'pinia'
import api from '../api'
import { ElMessage } from 'element-plus'
import {
  bestMatchSegments,
  spliceReplacedSegments,
  replaceParagraphText,
  insertParagraphText,
  deleteParagraphText,
  renumberSiblingsAfterInsert,
  SUBITEM_RE,
} from './review-diff'

/** 构造匹配 subNo 行首编号的正则（支持 X.Y / X.Y(Z) / 全角括号 → 归一后比对） */
function subNoLineRe(subNo) {
  const variants = new Set([subNo, subNo.replace(/[(（][0-9０-９a-zA-Z]+[)）]/g, '')])
  const body = [...variants]
    .filter(Boolean)
    .map((v) =>
      v
        .replace(/\./g, '\\.')
        .replace(/\(/g, '[(（]')
        .replace(/\)/g, '[)）]'),
    )
    .join('|')
  return new RegExp(`^[\\s　]*(?:${body})[\\s　:：、]`)
}

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

    async startReview() {
      if (!this.reviewId) {
        ElMessage.error('请先上传合同')
        return
      }
      await api.post(`/review/${this.reviewId}/start`)
      this.phase = 'processing'
      this.status = 'processing'
      this.progress = { percent: 0, stage: '正在准备条款审查' }
      this.poll()
    },

    poll() {
      clearTimeout(this.pollingTimer)
      if (!this.reviewId) return
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
      ElMessage.success('合同审查完成')
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
     * - 若 subNo 非空，定位原 text 中以该编号开头的行替换（含 X.Y(Z)/全角括号）；
     * - 若 finalText 不带原编号，自动把原行字面编号前缀补回去；
     * - 若无 subNo 且 finalText 是单段带 X.Y，回退到按该 X.Y 处理；
     * - 其它情况（整条款多段替换）：仅替换首行之后的正文行，标题行保留。
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
        const re = subNoLineRe(subNo)
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

      // 整条款替换：标题行（第X条）保留，从首个正文行开始替换；
      // 原行数多于新行数时截断，新行更多时追加。
      const firstBodyIdx = lines.findIndex((ln) => !/^\s*第[一二三四五六七八九十百零〇\d]+条/.test(ln))
      const start = firstBodyIdx > 0 ? firstBodyIdx : 0
      const out = [...lines]
      for (let i = 0; i < newLines.length; i++) {
        const target = start + i
        if (target < out.length) out[target] = newLines[i]
        else out.push(newLines[i])
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
        const op = d.operation || risk?.operation || 'replace'
        const subNo = d.sub_item_no || risk?.sub_item_no || ''
        const anchorClauseId = d.anchor_clause_id || risk?.anchor_clause_id || clauseId
        const anchorSubNo = d.anchor_sub_item_no || risk?.anchor_sub_item_no || ''

        if (op === 'insert_after' || op === 'insert_before') {
          const position = op === 'insert_after' ? 'after' : 'before'
          // 跨条款插入：先按锚点子项找到所在 clause，插入；前端多 clause 由后端负责跨条款导出，
          // 这里仍写到当前 clauseId 的 visual（仅本地展示，导出以最终后端为准）。
          html = insertParagraphText(html, anchorSubNo, finalText, position)
          // 插入新编号后重排同级兄弟编号（2.1/2.2/2.3 之间插 2.2 → 2.3/2.4），
          // 避免 1,2,2 重复编号
          const insM = SUBITEM_RE.exec(finalText.trim())
          if (insM) html = renumberSiblingsAfterInsert(html, insM[1], finalText.trim())
          text = this._applyLineInsert(text, anchorSubNo, finalText, position)
          continue
        }

        if (op === 'delete') {
          html = deleteParagraphText(html, subNo)
          text = this._applyLineDelete(text, subNo)
          continue
        }

        // replace：精确按子项编号替换目标行的编号后正文；保留标题与其它行
        if (subNo) {
          const out = replaceParagraphText(html, subNo, finalText)
          if (out !== null && out !== undefined) html = out
          // 定位失败 → 不乱替换（保留原文），决策在导出时由后端提示
        } else {
          // 整条款：保留标题行，替换正文行（不再 Jaccard 乱猜段落）
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

    /** 在原 text 中 anchor 子项行 后/前 插入新单位文本（支持 X.Y(Z)/全角括号） */
    _applyLineInsert(originalText, anchorSubNo, newText, position) {
      const lines = originalText.split(/\r?\n/)
      if (!lines.length) return newText
      if (anchorSubNo) {
        const re = subNoLineRe(anchorSubNo)
        const idx = lines.findIndex((ln) => re.test(ln.trim()))
        if (idx >= 0) {
          const insertAt = position === 'after' ? idx + 1 : idx
          lines.splice(insertAt, 0, newText)
          return lines.join('\n')
        }
      }
      // 兜底：追加到末尾 / 头部
      if (position === 'before') lines.unshift(newText)
      else lines.push(newText)
      return lines.join('\n')
    },

    /** 从原 text 中删除指定子项行（支持 X.Y(Z)/全角括号） */
    _applyLineDelete(originalText, subNo) {
      if (!subNo) return originalText
      const re = subNoLineRe(subNo)
      const out = originalText.split(/\r?\n/).filter((ln) => !re.test(ln.trim()))
      return out.join('\n')
    },

    /** 决策：本地乐观更新 + 后端保存 */
    async saveDecision(risk, type, payload = {}) {
      const decision = {
        risk_id: risk.risk_id,
        type,
        text: payload.text ?? (type === 'accepted' ? risk.suggestion : null),
        reason: payload.reason ?? null,
        sub_item_no: payload.sub_item_no ?? risk.sub_item_no ?? null,
        // Plan B：透传 operation / anchor / new 字段，导出按单位执行
        operation: payload.operation ?? risk.operation ?? null,
        anchor_clause_id: payload.anchor_clause_id ?? risk.anchor_clause_id ?? null,
        anchor_sub_item_no: payload.anchor_sub_item_no ?? risk.anchor_sub_item_no ?? null,
        new_clause_no: payload.new_clause_no ?? risk.new_clause_no ?? null,
        new_clause_title: payload.new_clause_title ?? risk.new_clause_title ?? null,
      }
      this.decisions = { ...this.decisions, [risk.risk_id]: decision }
      // 基于原始内容重新应用该条款所有决策（防止叠加漂移）
      // insert_* 的跨条款 effect 也尝试重建一次目标 clause（用于本机预览）
      this._rebuildClauseHtml(risk.clause_id)
      const op = decision.operation || 'replace'
      const anchorClauseId = decision.anchor_clause_id || risk.clause_id
      if ((op === 'insert_after' || op === 'insert_before') && anchorClauseId !== risk.clause_id) {
        this._rebuildClauseHtml(anchorClauseId)
      }
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
      // insert_* 跨条款 effect 也回滚一次
      const anchorClauseId = risk.anchor_clause_id
      if ((risk.operation === 'insert_after' || risk.operation === 'insert_before') && anchorClauseId && anchorClauseId !== clauseId) {
        this._rebuildClauseHtml(anchorClauseId)
      }
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
