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
      <article class="paper">
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

.hidden {
  display: none;
}
</style>
