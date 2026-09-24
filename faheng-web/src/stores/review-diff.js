/** 条款段落粒度替换工具（前端展示用）
 *
 * 思路：决策文本按行切段，每个段落在条款 HTML 中找最相似的原段落作为锚点，
 * 就地替换为带 "replaced" 标识的 <p>，其它原段落保持不变。
 *
 * 与后端 docx_export._replace_clause_span 的目标一致 —— 只动必须动的段落，
 * 保留原合同条款的其它段落、行内样式、表格等元素。
 */

/** 子项编号正则：X.Y 或 X.Y.Z，后面必须跟空白/全角空格/冒号/顿号 */
const SUBITEM_RE = /^\s*(\d+\.\d+(?:\.\d+)?)[\s　:：、]/

export { SUBITEM_RE }

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

/** 把 clause.html 按 <p> 顶层节点切成 [{raw, text, openTag, innerHtml}] 列表。
 * - 保留顶层 <p> 之间的其它节点（标题/列表/表格）原样拼接。
 * - openTag 是 <p ...> 开标签（含属性），用于按编号命中后只换 innerText。
 * - innerHtml 是 <p ...> 与 </p> 之间的原始 HTML（含 run 级 <span> 样式），
 *   用于保留字体/字号等行内格式。
 */
function splitParagraphs(html) {
  if (!html) return []
  const re = /<p\b([^>]*)>([\s\S]*?)<\/p>/gi
  const out = []
  let m
  while ((m = re.exec(html))) {
    const attrs = m[1] || ''
    const inner = m[2]
    const innerText = inner
      .replace(/<br\s*\/?>(\s*)/gi, '\n')
      .replace(/<[^>]+>/g, '')
    out.push({
      raw: m[0],
      text: innerText.trim(),
      openTag: `<p${attrs}>`,
      innerHtml: inner,
    })
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
      openTag: '<p class="replaced">',
      innerHtml: escapeHtml(m.replacement),
    }
  }
  return paragraphs.map((p) => p.raw).join('')
}

/** 在条款 HTML 中找到子项编号为 X.Y 的 <p> 下标（-1 表示没找到）。
 * 只匹配 <p> 顶层节点的首段纯文本，保证对齐 docx 解析的段落切分。
 */
export function findParagraphIndexBySubItemNo(clauseHtml, subItemNo) {
  if (!clauseHtml || !subItemNo) return -1
  const paragraphs = splitParagraphs(clauseHtml)
  for (let i = 0; i < paragraphs.length; i++) {
    const m = SUBITEM_RE.exec(paragraphs[i].text)
    if (m && m[1] === subItemNo) return i
  }
  return -1
}

/** 按子项编号就地替换原 <p> 的 innerText —— 保留 <p ...> 开标签与样式，
 * 仅追加 "replaced" class 让绿框样式生效。找不到子项编号时退化为按相似度兜底。
 *
 * @returns 替换后的 HTML
 */
export function replaceParagraphText(clauseHtml, subItemNo, newText) {
  if (!clauseHtml) return clauseHtml
  const paragraphs = splitParagraphs(clauseHtml)
  if (!paragraphs.length) {
    return `<p class="replaced">${escapeHtml(newText || '')}</p>`
  }
  let idx = subItemNo ? findParagraphIndexBySubItemNo(clauseHtml, subItemNo) : -1
  if (idx < 0) {
    // 兜底 1：尝试从 newText 开头抓 X.Y，再走相似度
    const m = newText && SUBITEM_RE.exec(newText)
    if (m) idx = findParagraphIndexBySubItemNo(clauseHtml, m[1])
  }
  if (idx < 0) {
    // 兜底 2：Jaccard 相似度（保留旧实现行为）
    const segments = (newText || '')
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean)
    if (segments.length === 1) {
      const matches = bestMatchSegments(paragraphs.map((p) => p.text).join('\n'), segments)
      return spliceReplacedSegments(clauseHtml, matches)
    }
    const matches = bestMatchSegments(paragraphs.map((p) => p.text).join('\n'), segments)
    return spliceReplacedSegments(clauseHtml, matches)
  }

  // 命中子项编号：保留 <p ...> 开标签 + run 级 <span> 字体样式，
  // 只换 innerText；class 追加 "replaced"。
  // 同时若新文本没有 X.Y 编号，自动把原段落开头的编号补回去，避免丢号。
  const target = paragraphs[idx]
  const replacedTag = withReplacedClass(target.openTag)
  const safeText = ensureSubItemNo(target.text, newText)
  const span = extractFirstSpanWrapper(target.innerHtml || '')
  const body = `${span.open}${escapeHtml(safeText || '')}${span.close}`
  paragraphs[idx] = {
    ...target,
    raw: `${replacedTag}${body}</p>`,
    text: (safeText || '').trim(),
    openTag: replacedTag,
    innerHtml: body,
  }
  return paragraphs.map((p) => p.raw).join('')
}

/** 提取 innerHtml 开头的 span open/close 标签。
 * - 如果以 `<span ...>` 开头并以 `</span>` 结尾，则返回该 span 的 open + close，
 *   用于包裹新文本以保留字体/字号等行内样式。
 * - 否则返回空 open/close（新文本直接放进 `<p>`）。
 */
function extractFirstSpanWrapper(innerHtml) {
  const trimmed = (innerHtml || '').trimStart()
  const m = trimmed.match(/^<span\b([^>]*?)>([\s\S]*?)<\/span>/i)
  if (!m) return { open: '', close: '' }
  return { open: `<span${m[1]}>`, close: '</span>' }
}

/** 若原段落以 X.Y 编号开头而 newText 不带相同编号，则把原编号补到 newText 前。 */
function ensureSubItemNo(originalText, newText) {
  const text = (newText || '').replace(/^\s+/, '')
  const origMatch = SUBITEM_RE.exec((originalText || '').trim())
  const newMatch = SUBITEM_RE.exec(text)
  if (!origMatch) return text
  // 新文本已有合法 X.Y 编号 → 原样返回（不重复补号）
  if (newMatch) return text
  // 原段落编号 + 空格 + 新文本
  return `${origMatch[0]}${text}`
}

/** 给 <p ...> 开标签追加 replaced class（保留原 style / class / data-* 等属性） */
function withReplacedClass(openTag) {
  const classMatch = openTag.match(/class\s*=\s*"([^"]*)"/i)
  if (classMatch) {
    const classes = classMatch[1].split(/\s+/).filter(Boolean)
    if (!classes.includes('replaced')) classes.push('replaced')
    return openTag.replace(/class\s*=\s*"[^"]*"/i, `class="${classes.join(' ')}"`)
  }
  // 已有属性但无 class：插入 class
  if (/>$/.test(openTag)) {
    return openTag.replace(/<p\b/, '<p class="replaced"')
  }
  return openTag.replace(/<p\b/, '<p class="replaced" ')
}

function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
}