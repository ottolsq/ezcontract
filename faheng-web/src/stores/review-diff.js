/** 条款段落粒度替换工具（前端展示用）
 *
 * 思路：决策文本按行切段，每个段落在条款 HTML 中找最相似的原段落作为锚点，
 * 就地替换为带 "replaced" 标识的 <p>，其它原段落保持不变。
 *
 * 与后端 docx_export._replace_clause_span 的目标一致 —— 只动必须动的段落，
 * 保留原合同条款的其它段落、行内样式、表格等元素。
 */

/** 子项编号正则：X.Y / X.Y.Z / X.Y(Z) / X.Y（Z）/ 独立（Z）/(a)，
 * 全角半角括号、全角数字均支持；编号后可跟分隔符（并入捕获，便于原样拼回）。
 * 注意：编号后不强制分隔符（真实合同 "（1）乙方…" 常无分隔符）。 */
const SUBITEM_RE =
  /^[\s　]*((?:\d+\.\d+(?:\.\d+)?(?:\([0-9０-９a-zA-Z]+\)|（[0-9０-９a-zA-Z]+）)*|(?:\([0-9０-９a-zA-Z]+\)|（[0-9０-９a-zA-Z]+）)+)[\s　:：、]*)/

export { SUBITEM_RE }

/** 编号 token 归一：全角括号→半角、全角数字→半角、去分隔符与空白，用于编号比对 */
function normNo(s) {
  return (s || '')
    .trim()
    .replace(/[\s　:：、]/g, '')
    .replace(/（/g, '(')
    .replace(/）/g, ')')
    .replace(/[０-９]/g, (d) => String.fromCharCode(d.charCodeAt(0) - 0xfee0))
}

/** X.Y(Z) → X.Y（去括号层级，用于基编号回退匹配） */
function baseNo(s) {
  return (s || '').replace(/[(（][0-9０-９a-zA-Z]+[)）]/g, '')
}

/** 取编号最内层括号内容（'7.2(1)' → '1'；'（a）' → 'a'；无括号 → null） */
function innermostToken(s) {
  const m = normNo(s).match(/\(([^()]+)\)$/)
  return m ? m[1] : null
}

/** 行的字面编号是否与 subItemNo 一致。
 * - 完整编号相等（1.1 ↔ 1.1 / 7.2（1）↔ 7.2(1)）；
 * - 双方均无内层时按基编号比对；
 * - 裸基项行（7.2 乙方违约）不算 7.2(1) 的匹配（避免父项误吃子项替换）。
 * 注意：行首只写内层的「（1）乙方…」不带父级上下文，本函数不匹配 ——
 * 由 lineMatchesNoInContext 带当前父级基编号做上下文比对。 */
export function lineMatchesNo(line, subItemNo) {
  const m = SUBITEM_RE.exec(line || '')
  if (!m) return false
  const p = normNo(m[1])
  const n = normNo(subItemNo)
  if (p === n) return true
  const pi = innermostToken(m[1])
  const ni = innermostToken(subItemNo)
  if (pi && ni) return false // 内层 token 相等不等于同一子项（6.1(3) ≠ 6.2(3)）
  if (!pi && !ni) return p === normNo(baseNo(subItemNo))
  return false
}

/** 带父级上下文的行匹配：currentBase 是该行所属的 X.Y 基编号。
 * 行首「（1）乙方…」只写内层编号，其父级由前一个 X.Y 行决定：
 * 只有 currentBase === subItemNo 的基编号时才算命中。 */
export function lineMatchesNoInContext(line, subItemNo, currentBase) {
  const m = SUBITEM_RE.exec(line || '')
  if (!m) return false
  const p = normNo(m[1])
  const n = normNo(subItemNo)
  if (p === n) return true
  // 行首只写内层（（3）…）且父级匹配
  const lineIsInnerOnly = /^[（(]/.test((m[1] || '').trim())
  const lineInner = innermostToken(m[1])
  const subInner = innermostToken(subItemNo)
  if (lineIsInnerOnly && lineInner && subInner) {
    return lineInner === subInner && currentBase === normNo(baseNo(subItemNo))
  }
  return lineMatchesNo(line, subItemNo)
}

/** 行的字面编号前缀（含尾随分隔符）的基编号（X.Y），非基编号行返回 null。 */
function lineBaseNo(line) {
  const m = SUBITEM_RE.exec(line || '')
  if (!m) return null
  const t = m[1].trim()
  if (/^[（(]/.test(t)) return null // 独立（Z）行无基编号
  return normNo(baseNo(t))
}

/** 条款标题行（第X条）—— 替换永不触碰 */
const CLAUSE_TITLE_RE = /^[\s　]*第[一二三四五六七八九十百零〇\d]+条/

export function isClauseTitleLine(line) {
  return CLAUSE_TITLE_RE.test((line || '').trim())
}

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

/** 按子项编号找 <p> 下标（支持 X.Y(Z) / 全角括号 / 独立（Z）行）。
 * 逐段逐行扫描，维护「当前父级基编号」上下文：
 * 行首 X.Y → 更新 currentBase；独立（Z）行属于 currentBase。
 * 这样 6.2(3) 不会误命中 6.1 下的（3）行。
 */
export function findParagraphIndexBySubItemNo(clauseHtml, subItemNo) {
  if (!clauseHtml || !subItemNo) return -1
  const paragraphs = splitParagraphs(clauseHtml)
  let currentBase = null
  for (let i = 0; i < paragraphs.length; i++) {
    const lines = paragraphs[i].text.split('\n')
    for (const ln of lines) {
      const b = lineBaseNo(ln)
      if (b) currentBase = b
      if (lineMatchesNoInContext(ln, subItemNo, currentBase)) return i
    }
  }
  return -1
}

/** 按子项编号就地替换目标行的编号后正文 —— 保留 <p ...> 开标签、行首编号
 * 与 run 级样式；同段多子项（w:br 分行）时仅替换目标行，其余行原样保留。
 *
 * 定位失败时返回 null（由调用方决定是否兜底/提示），不再自动 Jaccard 乱替换。
 *
 * @returns 替换后的 HTML；null = 未定位到目标段
 */
export function replaceParagraphText(clauseHtml, subItemNo, newText) {
  if (!clauseHtml) return clauseHtml
  const paragraphs = splitParagraphs(clauseHtml)
  if (!paragraphs.length) return null
  let idx = subItemNo ? findParagraphIndexBySubItemNo(clauseHtml, subItemNo) : -1
  if (idx < 0) {
    // 兜底：尝试从 newText 开头抓编号，再定位一次
    const m = newText && SUBITEM_RE.exec(newText)
    if (m) idx = findParagraphIndexBySubItemNo(clauseHtml, m[1])
  }
  if (idx < 0) return null

  // 子标题行保护（与后端 _is_subitem_heading_line 对齐）：
  // 「编号 + ≤12字短名称 + 下方有内容行」是子标题（如「3.1 租金标准」），
  // 替换落到其下第一条内容行（（Z）嵌套行 / 正文段），子标题行原样保留。
  const shifted = shiftHeadingToContent(paragraphs, idx, subItemNo)
  if (shifted !== null) idx = shifted

  const target = paragraphs[idx]
  const lines = target.text.split('\n')
  // 目标行：整段无换行 → 第 0 行；多行 → 带父级上下文编号匹配的行
  let lineIdx = 0
  if (lines.length > 1 && subItemNo) {
    const found = findLineIdxWithContext(paragraphs, idx, subItemNo)
    if (found >= 0) lineIdx = found
  }
  // 行首字面编号前缀（含尾随分隔符），替换后自动补回，不丢号
  const line = lines[lineIdx]
  const pm = SUBITEM_RE.exec(line)
  const prefix = pm ? pm[0] : ''
  const body = (newText || '').replace(/^[\s　]+/, '')
  lines[lineIdx] = prefix && !body.startsWith(prefix.trim()) ? `${prefix}${body}` : body

  // 保留原 <p> 开标签 + 首个 span 的行内样式；class 追加 replaced
  const replacedTag = withReplacedClass(target.openTag)
  const span = extractFirstSpanWrapper(target.innerHtml || '')
  const bodyHtml = `${span.open}${escapeHtml(lines.join('\n'))}${span.close}`
  paragraphs[idx] = {
    ...target,
    raw: `${replacedTag}${bodyHtml}</p>`,
    text: lines.join('\n'),
    openTag: replacedTag,
    innerHtml: bodyHtml,
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

/** 在 anchor <p> 后/前插入新 <p>，样式复制 anchor 开标签。
 *
 * @param clauseHtml 原条款 HTML
 * @param anchorSubItemNo 锚点子项编号（空字符串表示条款首/末尾）
 * @param newText 新单位完整文本
 * @param position 'after' | 'before'
 * @returns 插入后的 HTML
 */
export function insertParagraphText(clauseHtml, anchorSubItemNo, newText, position = 'after') {
  if (!clauseHtml) return clauseHtml
  const paragraphs = splitParagraphs(clauseHtml)
  const text = (newText || '').trim()
  if (!text) return clauseHtml

  // 没 <p> 兜底：直接包成新段落
  if (!paragraphs.length) {
    const block = `<p class="inserted">${escapeHtml(text)}</p>`
    return position === 'before' ? `${block}${clauseHtml}` : `${clauseHtml}${block}`
  }

  // 定位锚点
  let anchorIdx = -1
  if (anchorSubItemNo) anchorIdx = findParagraphIndexBySubItemNo(clauseHtml, anchorSubItemNo)
  if (anchorIdx < 0) {
    // 兜底：尝试从 newText 开头抓 X.Y 编号作为锚点
    const m = SUBITEM_RE.exec(text)
    if (m) anchorIdx = findParagraphIndexBySubItemNo(clauseHtml, m[1])
  }
  if (anchorIdx < 0) anchorIdx = position === 'after' ? paragraphs.length - 1 : 0

  const anchor = paragraphs[anchorIdx]
  // 同段多子项（w:br 分行）：把新行插到目标行之后/之前（行内插入），而非另起 <p>
  const anchorLines = anchor.text.split('\n')
  if (anchorSubItemNo && anchorLines.length > 1) {
    const lineIdx = findLineIdxWithContext(paragraphs, anchorIdx, anchorSubItemNo)
    if (lineIdx >= 0) {
      const insertAtLine = position === 'after' ? lineIdx + 1 : lineIdx
      anchorLines.splice(insertAtLine, 0, text)
      const replacedTag = withReplacedClass(anchor.openTag)
      const span = extractFirstSpanWrapper(anchor.innerHtml || '')
      const bodyHtml = `${span.open}${escapeHtml(anchorLines.join('\n'))}${span.close}`
      paragraphs[anchorIdx] = {
        ...anchor,
        raw: `${replacedTag}${bodyHtml}</p>`,
        text: anchorLines.join('\n'),
        openTag: replacedTag,
        innerHtml: bodyHtml,
      }
      return paragraphs.map((p) => p.raw).join('')
    }
  }
  // 复制 anchor openTag，仅调整 class 标识 inserted
  let newOpen = anchor.openTag
  if (/<p\b/i.test(newOpen)) {
    // 移除原 class 里的 replaced，追加 inserted
    newOpen = newOpen.replace(/class\s*=\s*"([^"]*)"/i, (_, c) => {
      const filtered = c.split(/\s+/).filter(Boolean).filter((x) => x !== 'replaced')
      filtered.push('inserted')
      return `class="${filtered.join(' ')}"`
    })
    if (!/class\s*=/i.test(newOpen)) {
      newOpen = newOpen.replace(/<p\b/, '<p class="inserted"')
    }
  } else {
    newOpen = '<p class="inserted">'
  }
  // 复制 anchor 的 span 包裹（保留字体/字号等行内样式）
  const span = extractFirstSpanWrapper(anchor.innerHtml || '')
  const safeText = ensureSubItemNo('', text) // 新单位自带编号，不强制补编号
  const newP = {
    raw: `${newOpen}${span.open}${escapeHtml(safeText)}${span.close}</p>`,
    text: safeText,
    openTag: newOpen,
    innerHtml: `${span.open}${escapeHtml(safeText)}${span.close}`,
  }

  const insertAt = position === 'after' ? anchorIdx + 1 : anchorIdx
  paragraphs.splice(insertAt, 0, newP)
  return paragraphs.map((p) => p.raw).join('')
}

/** 插入新子项后重排同级编号：从插入的编号起，把后续同级子项编号依次 +1。
 * 例：2.1/2.2/2.3 之间插入新 2.2 → 原 2.2→2.3、2.3→2.4（同 X 前缀的 Y 序列）。
 * 嵌套（Z）：7.2 下（1）（2）之间插新（2）→ 原（2）→（3）、（3）→（4）。
 * 新插入的内容行（文本 === insertedText，含 inserted class 段）跳过。 */
export function renumberSiblingsAfterInsert(clauseHtml, insertedNo, insertedText = '') {
  if (!clauseHtml || !insertedNo) return clauseHtml
  const m = SUBITEM_RE.exec(insertedNo.trim())
  if (!m) return clauseHtml
  const inserted = m[1].trim()
  // 归一插入编号：X.Y(Z) / 纯（Z）→ 父级 + 内层 Z；纯 X.Y → X 前缀 + 序号 Y
  const insInner = innermostToken(inserted) // '7.2(2)'→'2'；'（2）'→'2'；'2.2'→null
  const insBaseTok = insInner !== null ? inserted.replace(/[（(][^）)]+[）)]\s*$/, '').trim() : inserted
  const insParent = insInner !== null ? normNo(insBaseTok) : null // '7.2'；纯（Z）时 ''
  const insX = insInner === null ? (inserted.match(/^(\d+)\./)?.[1] ?? null) : null
  const insY = insInner === null ? (inserted.match(/\.(\d+)$/)?.[1] ?? null) : null
  if (insInner === null && (insX === null || insY === null)) return clauseHtml

  const paragraphs = splitParagraphs(clauseHtml)
  const skipText = (insertedText || '').trim()
  let started = false
  let currentParent = null
  for (let i = 0; i < paragraphs.length; i++) {
    const p = paragraphs[i]
    const isNewInsert = /class\s*=\s*"[^"]*\binserted\b/.test(p.openTag)
    const lines = p.text.split('\n')
    let changed = false
    for (let li = 0; li < lines.length; li++) {
      const lm = SUBITEM_RE.exec(lines[li])
      if (!lm) continue
      const tok = lm[1].trim()
      const tokInnerOnly = /^[（(]/.test(tok)
      let sameLevel = false
      let curNo = null
      if (insInner === null) {
        // X.Y 插入：同级 = 同 X 前缀的基项行（2.2/2.3 都属于 X=2）
        const tokX = tok.match(/^(\d+)\./)?.[1] ?? null
        if (!tokInnerOnly && tokX === insX) {
          sameLevel = true
          curNo = tok.match(/\.(\d+)$/)?.[1] ?? null
        }
      } else {
        // （Z）/ X.Y(Z) 插入：同级 = 同父级下的内层行
        if (tokInnerOnly && currentParent !== null && currentParent === insParent) {
          sameLevel = true
          curNo = innermostToken(tok)
        }
      }
      // 维护父级上下文（X.Y 行更新 currentParent，供后续（Z）行判级）
      if (!tokInnerOnly) currentParent = normNo(baseNo(tok))
      if (!sameLevel || curNo === null) continue
      // 新插入内容行跳过（行文本与 insertedText 一致）
      if (skipText && (lines[li].trim() === skipText || lines[li].includes(skipText))) continue
      if (!started) {
        if (Number(curNo) < Number(insInner ?? insY)) continue
        started = true
      }
      if (tokInnerOnly) {
        const newInner = bumpInnerToken(curNo)
        lines[li] = lines[li].replace(/^[（(][^）)]+[）)]/, (s) =>
          s.replace(/[^（()）]+/, newInner),
        )
      } else {
        const newTok = tok.replace(/(\.\d+)$/, (s) => `.${Number(s.slice(1)) + 1}`)
        lines[li] = lines[li].replace(lm[0], lm[0].replace(tok, newTok))
      }
      changed = true
    }
    if (changed) {
      const replacedTag = withReplacedClass(p.openTag)
      const span = extractFirstSpanWrapper(p.innerHtml || '')
      const bodyHtml = `${span.open}${escapeHtml(lines.join('\n'))}${span.close}`
      paragraphs[i] = {
        ...p,
        raw: `${replacedTag}${bodyHtml}</p>`,
        text: lines.join('\n'),
        openTag: replacedTag,
        innerHtml: bodyHtml,
      }
    }
  }
  return paragraphs.map((p) => p.raw).join('')
}

/** （Z）token 序号 +1：（3）→（4）；（a）→（b）；（z）→（aa）循环。 */
function bumpInnerToken(t) {
  if (/^\d+$/.test(t)) return String(Number(t) + 1)
  const s = t.toLowerCase()
  if (!/^[a-z]+$/.test(s)) return t
  let num = 0
  for (const ch of s) num = num * 26 + (ch.charCodeAt(0) - 96)
  num += 1
  let out = ''
  while (num > 0) {
    const r = (num - 1) % 26
    out = String.fromCharCode(97 + r) + out
    num = Math.floor((num - 1) / 26)
  }
  return out
}

/** 同段多行时按父级上下文找目标行号；找不到返回 -1。 */
function findLineIdxWithContext(paragraphs, idx, subItemNo) {
  const lines = paragraphs[idx].text.split('\n')
  let currentBase = null
  // 本段之前的最后基编号作为初始上下文
  for (let i = 0; i < idx; i++) {
    for (const ln of paragraphs[i].text.split('\n')) {
      const b = lineBaseNo(ln)
      if (b) currentBase = b
    }
  }
  for (let li = 0; li < lines.length; li++) {
    const b = lineBaseNo(lines[li])
    if (b) currentBase = b
    if (lineMatchesNoInContext(lines[li], subItemNo, currentBase)) return li
  }
  return -1
}

/** 子标题行检测 + 替换目标下移（与后端 _is_subitem_heading_line /
 * _shift_to_first_content_below 对齐）。
 * 目标段是「编号 + 短名称（≤12字，无标点）」且下方（同段后续行 / 后续段
 * 的（Z）行或正文）有内容行 → 返回内容行所在段下标；否则返回 null。 */
function shiftHeadingToContent(paragraphs, idx, subItemNo) {
  if (!subItemNo) return null
  const target = paragraphs[idx]
  const lines = target.text.split('\n')
  // 仅看编号匹配的首行
  let lineIdx = 0
  if (lines.length > 1) {
    const found = findLineIdxWithContext(paragraphs, idx, subItemNo)
    if (found < 0) return null
    lineIdx = found
  } else if (!lineMatchesNo(lines[0], subItemNo)) {
    return null
  }
  const line = lines[lineIdx]
  const pm = SUBITEM_RE.exec(line)
  if (!pm) return null
  const rest = line.slice(pm[0].length).trim()
  if (!rest || rest.length > 12) return null
  if (/[。；;，,]/.test(rest)) return null
  // 下方内容：同段后续非空行
  if (lineIdx + 1 < lines.length && lines[lineIdx + 1].trim()) return idx
  // 跨段：后续段的（Z）/正文（遇到下一个 X.Y 基编号或标题行停）
  for (let i = idx + 1; i < paragraphs.length; i++) {
    const first = paragraphs[i].text.split('\n')[0].trim()
    if (!first) continue
    if (isClauseTitleLine(first)) return null
    const bm = SUBITEM_RE.exec(first)
    if (bm && !/^[（(]/.test(bm[1].trim())) return null // 下一个 X.Y 子项 → 无内容行
    return i
  }
  return null
}

/** 删除指定子项：整段独占时删 <p>；同段多子项（w:br 分行）时仅删目标行。 */
export function deleteParagraphText(clauseHtml, subItemNo) {
  if (!clauseHtml) return clauseHtml
  if (!subItemNo) return clauseHtml
  const paragraphs = splitParagraphs(clauseHtml)
  if (!paragraphs.length) return clauseHtml
  const idx = findParagraphIndexBySubItemNo(clauseHtml, subItemNo)
  if (idx < 0) return clauseHtml
  const target = paragraphs[idx]
  const lines = target.text.split('\n')
  if (lines.length > 1) {
    // 同段多子项：只删目标行，其余行保留
    const lineIdx = findLineIdxWithContext(paragraphs, idx, subItemNo)
    if (lineIdx >= 0) {
      lines.splice(lineIdx, 1)
      const replacedTag = withReplacedClass(target.openTag)
      const span = extractFirstSpanWrapper(target.innerHtml || '')
      const bodyHtml = `${span.open}${escapeHtml(lines.join('\n'))}${span.close}`
      paragraphs[idx] = {
        ...target,
        raw: `${replacedTag}${bodyHtml}</p>`,
        text: lines.join('\n'),
        openTag: replacedTag,
        innerHtml: bodyHtml,
      }
      return paragraphs.map((p) => p.raw).join('')
    }
  }
  paragraphs.splice(idx, 1)
  return paragraphs.map((p) => p.raw).join('')
}

function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
}