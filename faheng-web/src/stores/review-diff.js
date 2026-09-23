/** 条款段落粒度替换工具（前端展示用）
 *
 * 思路：决策文本按行切段，每个段落在条款 HTML 中找最相似的原段落作为锚点，
 * 就地替换为带 "replaced" 标识的 <p>，其它原段落保持不变。
 *
 * 与后端 docx_export._replace_clause_span 的目标一致 —— 只动必须动的段落，
 * 保留原合同条款的其它段落、行内样式、表格等元素。
 */

/** 移除标点和空白，便于相似度比较 */
function normalize(s) {
  return s
    .replace(/[\s　，,。.；;：:！!？?()（）【】\[\]<>《》""'']/g, '')
    .toLowerCase()
}

/** 字符级 Jaccard 相似度（适合短文本） */
function similarity(a, b) {
  const sa = new Set(normalize(a))
  const sb = new Set(normalize(b))
  if (!sa.size || !sb.size) return 0
  let inter = 0
  for (const c of sa) if (sb.has(c)) inter++
  return (inter / (sa.size + sb.size - inter))
}

/** 把 clause.html 按 <p> 顶层节点切成 [{text, html}] 列表。
 * - 保留顶层 <p> 之间的其它节点（标题/列表/表格）原样拼接。
 * - 跳过 <preamble>/<tail> 类前置块（避免误匹配）。
 */
function splitParagraphs(html) {
  if (!html) return []
  const re = /<p\b[^>]*>([\s\S]*?)<\/p>/gi
  const out = []
  let m
  while ((m = re.exec(html))) {
    const inner = m[1].replace(/<br\s*\/?>(\s*)/gi, '\n').replace(/<[^>]+>/g, '')
    out.push({ raw: m[0], text: inner.trim() })
  }
  return out
}

/** 把 segments 每个段落匹配到 clauses 段落中最相似的一项。
 * 返回 [{ origIdx, replacement }, ...]
 * 每个 replacement 必须落到一个最相似的原段落（不追加新增段落）。
 */
export function bestMatchSegments(clauseText, segments) {
  // 先按行粗切，再与 clause.text(原始) 比对。
  // 这里以 clauseText 的行作为候选锚点集合，更稳。
  const origLines = clauseText
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean)
  if (!origLines.length) return segments.map((replacement) => ({ origIdx: 0, replacement }))

  const used = new Set()
  const matches = []
  for (const replacement of segments) {
    let bestIdx = 0
    let bestScore = -1
    for (let i = 0; i < origLines.length; i++) {
      // 已被占用的段落允许再次复用（替换它），保持与 spliceReplacedSegments 的顺序匹配
      const s = similarity(origLines[i], replacement)
      if (s > bestScore) {
        bestScore = s
        bestIdx = i
      }
    }
    matches.push({ origIdx: bestIdx, replacement })
    used.add(bestIdx)
  }
  return matches
}

/** 把 matches 描述的替换落到 clauseHtml 上。
 * 所有 matches 都按 origIdx 替换为带 replaced 标记的 <p>，不会追加。
 */
export function spliceReplacedSegments(clauseHtml, matches) {
  const paragraphs = splitParagraphs(clauseHtml)
  if (!paragraphs.length) {
    // 没有原 <p>（罕见），直接包成替换段落
    return matches
      .map((m) => `<p class="replaced">${escapeHtml(m.replacement)}</p>`)
      .join('')
  }

  // 替换原文段落：从后往前，避免索引位移
  const ordered = [...matches].sort((a, b) => b.origIdx - a.origIdx)
  for (const m of ordered) {
    const idx = Math.max(0, Math.min(m.origIdx, paragraphs.length - 1))
    paragraphs[idx] = {
      raw: `<p class="replaced">${escapeHtml(m.replacement)}</p>`,
      text: m.replacement,
    }
  }
  return paragraphs.map((p) => p.raw).join('')
}

function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
}