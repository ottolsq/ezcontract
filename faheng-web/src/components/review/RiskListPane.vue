<script setup>
import { computed } from 'vue'
import { useReviewStore } from '../../stores/review'

const store = useReviewStore()

const decisionLabel = { accepted: '已采纳', modified: '已修改', rejected: '不采纳' }

const pendingByLevel = computed(
  () =>
    (level) =>
      store.risks.filter((r) => r.level === level && !store.decisions[r.risk_id]).length,
)
</script>

<template>
  <el-card class="risk-pane" shadow="never">
    <template #header>
      <div class="head">
        <span>风险清单</span>
        <el-tag size="small" type="info">
          处理 {{ store.processedCount }} / {{ store.risks.length }}
        </el-tag>
      </div>
    </template>

    <!-- 等级过滤 -->
    <div class="filters">
      <el-button
        :type="store.filters.level === 'high' ? 'primary' : ''"
        size="small"
        @click="store.filters.level = 'high'"
      >
        高风险（{{ store.stats.high }}）
      </el-button>
      <el-button
        :type="store.filters.level === 'medium' ? 'primary' : ''"
        size="small"
        @click="store.filters.level = 'medium'"
      >
        中风险（{{ store.stats.medium }}）
      </el-button>
    </div>
    <!-- 状态过滤 -->
    <div class="filters">
      <el-button
        :type="store.filters.status === 'pending' ? 'primary' : ''"
        size="small"
        @click="store.filters.status = 'pending'"
      >
        待处理（{{ pendingByLevel(store.filters.level) }}）
      </el-button>
      <el-button
        :type="store.filters.status === 'processed' ? 'primary' : ''"
        size="small"
        @click="store.filters.status = 'processed'"
      >
        已处理
      </el-button>
    </div>

    <div class="list">
      <button
        v-for="r in store.visibleRisks"
        :key="r.risk_id"
        class="risk-item"
        :class="{
          active: r.risk_id === store.currentRiskId,
          high: r.level === 'high',
          medium: r.level === 'medium',
        }"
        @click="store.currentRiskId = r.risk_id"
      >
        <span class="dot" />
        <span class="body">
          <span class="name">{{ r.title }}</span>
          <span class="meta">
            {{ r.clause_no }}
            <em v-if="store.decisions[r.risk_id]">
              · {{ decisionLabel[store.decisions[r.risk_id].type] }}
            </em>
          </span>
        </span>
      </button>
      <el-empty
        v-if="!store.visibleRisks.length"
        :description="store.filters.status === 'processed' ? '暂无已处理风险' : '当前等级风险已全部处理'"
        :image-size="60"
      />
    </div>
  </el-card>
</template>

<style scoped>
.risk-pane {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.risk-pane :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.filters {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

.list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.risk-item {
  width: 100%;
  display: grid;
  grid-template-columns: 8px 1fr;
  gap: 10px;
  padding: 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  text-align: left;
  margin-bottom: 2px;
}

.risk-item:hover {
  background: #f4f7fb;
}

.risk-item.active {
  background: #eaf2ff;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 6px;
  background: #3498db;
}

.risk-item.high .dot {
  background: #e74c3c;
}

.risk-item.medium .dot {
  background: #f39c12;
}

.body {
  min-width: 0;
}

.name {
  display: block;
  font-weight: 500;
  font-size: 13px;
}

.meta {
  display: block;
  color: #66758a;
  font-size: 12px;
  margin-top: 3px;
  font-style: normal;
}

.meta em {
  color: #087a55;
  font-style: normal;
}
</style>
