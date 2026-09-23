<script setup>
import { ref } from 'vue'
import { useReviewStore } from '../../stores/review'

const store = useReviewStore()
const scrollEl = ref(null)

/** 暴露给父组件：滚动到指定条款 */
function scrollToClause(clauseId) {
  const el = document.getElementById(`clause-${clauseId}`)
  if (el && scrollEl.value) {
    scrollEl.value.scrollTo({ top: el.offsetTop - 60, behavior: 'smooth' })
  }
}

defineExpose({ scrollToClause })
</script>

<template>
  <el-card class="contract-pane" shadow="never">
    <template #header>
      <div class="head">
        <span>合同正文</span>
        <span class="file">{{ store.filename }}</span>
      </div>
    </template>
    <div ref="scrollEl" class="doc-scroll">
      <article class="paper docx-prose">
        <!-- 首条款前：标题/编号/双方信息等（保持原文样式） -->
        <div
          v-if="store.preambleHtml"
          id="clause-preamble"
          class="clause-block preamble"
          v-html="store.preambleHtml"
        />
        <div
          v-for="c in store.clauses"
          :key="c.clause_id"
          :id="`clause-${c.clause_id}`"
          class="clause-block"
          :class="{
            'active-high':
              store.currentRisk?.clause_id === c.clause_id && store.currentRisk?.level === 'high',
            'active-medium':
              store.currentRisk?.clause_id === c.clause_id && store.currentRisk?.level === 'medium',
            decided: store.risks.some(
              (r) =>
                r.clause_id === c.clause_id &&
                ['accepted', 'modified'].includes(store.decisions[r.risk_id]?.type),
            ),
          }"
          v-html="c.html || c.text"
        />
        <!-- 签署栏：不参与审查，导出原样保留 -->
        <div
          v-if="store.tailHtml"
          id="clause-tail"
          class="clause-block tail"
          v-html="store.tailHtml"
        />
      </article>
    </div>
  </el-card>
</template>

<style scoped>
.contract-pane {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.contract-pane :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.file {
  color: #66758a;
  font-size: 12px;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
}

.paper {
  background: #fff;
  width: 100%;
  max-width: 210mm;
  margin: 0 auto;
  padding: 28mm 25mm;
  border: 1px solid #e4e9f2;
  border-radius: 6px;
  box-shadow: 0 6px 20px rgba(36, 89, 169, 0.08);
  font-family: '仿宋', '仿宋_GB2312', 'Times New Roman', serif;
  font-size: 12pt;
  line-height: 1.5;
  color: #000;
  box-sizing: border-box;
}

.paper :deep(.clause-block) {
  margin: 0;
}

/* 复刻 RichEditor 的 .docx-prose 样式：保证审查页和起草页视觉一致 */
.paper :deep(p) {
  margin: 0 0 8px;
  text-indent: 0;
}

.paper :deep(strong) {
  font-weight: bold;
}

.paper :deep(h1),
.paper :deep(h2),
.paper :deep(h3),
.paper :deep(h4) {
  padding-left: 0;
  margin-left: 0;
  text-indent: 0;
}

.paper :deep(h1) {
  font-family: '黑体', '仿宋', 'Times New Roman', serif;
  font-size: 22pt;
  text-align: center;
  font-weight: bold;
  margin: 0 0 18px;
}

.paper :deep(h2) {
  font-family: '黑体', 'Times New Roman', serif;
  font-size: 14pt;
  font-weight: bold;
  margin: 18px 0 10px;
}

.paper :deep(h3) {
  font-family: '黑体', 'Times New Roman', serif;
  font-size: 12pt;
  font-weight: bold;
  margin-top: 8px;
  margin-bottom: 6px;
}

.paper :deep(h4) {
  font-family: '黑体', 'Times New Roman', serif;
  font-size: 12pt;
  font-weight: bold;
  margin-top: 4px;
  margin-bottom: 4px;
}

.paper :deep(h3 + p),
.paper :deep(h4 + p) {
  text-indent: 0;
}

.paper :deep(blockquote) {
  text-indent: 0;
  margin: 6px 0 8px;
  padding: 0;
  border-left: none;
  color: inherit;
}

.paper :deep(blockquote p) {
  text-indent: 0;
  margin: 0;
}

.paper :deep(ul),
.paper :deep(ol) {
  padding-left: 28px;
  margin: 6px 0 8px;
}

.paper :deep(li) {
  margin: 2px 0;
}

.paper :deep(li > p) {
  text-indent: 0;
}

.paper :deep(table) {
  border-collapse: collapse;
  table-layout: fixed;
  width: 100%;
  margin: 8px 0;
}

.paper :deep(th),
.paper :deep(td) {
  border: 1px solid #1d2b4f;
  padding: 6px 8px;
  vertical-align: top;
}

.paper :deep(th) {
  background: #f0f4fa;
  font-weight: bold;
  text-align: center;
}

.hidden {
  display: none;
}
</style>
