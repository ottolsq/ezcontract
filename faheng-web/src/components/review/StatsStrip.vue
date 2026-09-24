<script setup>
import { useReviewStore } from '../../stores/review'

const store = useReviewStore()

const levelColor = { high: '#e74c3c', medium: '#f39c12', low: '#3498db' }
</script>

<template>
  <div class="stats">
    <div class="metric danger">
      <span>合同风险分</span>
      <strong>{{ store.liveScore }} / 100</strong>
    </div>
    <div class="metric">
      <span>高风险</span>
      <strong :style="{ color: levelColor.high }">{{ store.stats.high }}</strong>
    </div>
    <div class="metric">
      <span>中风险</span>
      <strong :style="{ color: levelColor.medium }">{{ store.stats.medium }}</strong>
    </div>
    <div class="metric">
      <span>处理进度</span>
      <strong>{{ store.processedCount }} / {{ store.risks.length }}</strong>
    </div>
    <div class="metric">
      <span>条款总数</span>
      <strong>{{ store.clauses.length }}</strong>
    </div>
  </div>
</template>

<style scoped>
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.metric {
  background: #fff;
  border: 1px solid #e4e9f2;
  border-radius: 10px;
  padding: 12px 16px;
}

.metric span {
  display: block;
  color: #66758a;
  font-size: 12px;
  margin-bottom: 4px;
}

.metric strong {
  font-size: 20px;
  font-weight: 600;
}

.metric.danger strong {
  color: #e74c3c;
}
</style>
