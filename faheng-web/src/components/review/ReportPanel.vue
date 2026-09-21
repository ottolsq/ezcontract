<script setup>
import { useReviewStore } from '../../stores/review'

const store = useReviewStore()

const decisionLabel = { accepted: '已采纳', modified: '已修改后采纳', rejected: '不采纳' }
const levelLabel = { high: '高风险', medium: '中风险', low: '低风险' }
</script>

<template>
  <div class="report">
    <el-alert
      v-if="store.processedCount < store.risks.length"
      type="warning"
      :closable="false"
      class="warn"
      :title="`仍有 ${store.risks.length - store.processedCount} 项风险待处理，建议完成处理后再导出最终合同`"
    />

    <div class="summary">
      <div class="stat">
        <span>合同风险分</span>
        <strong>{{ store.score }} / 100</strong>
      </div>
      <div class="stat">
        <span>风险总数</span>
        <strong>{{ store.risks.length }}</strong>
      </div>
      <div class="stat">
        <span>已处理</span>
        <strong>{{ store.processedCount }}</strong>
      </div>
      <div class="stat">
        <span>高风险</span>
        <strong>{{ store.stats.high }}</strong>
      </div>
    </div>

    <el-card shadow="never">
      <template #header>风险处理明细</template>
      <el-table :data="store.risks" size="small" stripe>
        <el-table-column prop="clause_no" label="条款" width="90" />
        <el-table-column prop="title" label="风险" min-width="150" />
        <el-table-column label="等级" width="80">
          <template #default="{ row }">{{ levelLabel[row.level] }}</template>
        </el-table-column>
        <el-table-column label="决策" width="110">
          <template #default="{ row }">
            <el-tag
              v-if="store.decisions[row.risk_id]"
              :type="
                store.decisions[row.risk_id].type === 'rejected' ? 'info' : 'success'
              "
              size="small"
            >
              {{ decisionLabel[store.decisions[row.risk_id].type] }}
            </el-tag>
            <el-tag v-else type="warning" size="small">待处理</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="180">
          <template #default="{ row }">
            <span v-if="store.decisions[row.risk_id]?.reason">
              {{ store.decisions[row.risk_id].reason }}
            </span>
            <span v-else-if="store.decisions[row.risk_id]?.text">
              {{ store.decisions[row.risk_id].text.slice(0, 50) }}…
            </span>
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.warn {
  margin-bottom: 14px;
}

.summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.stat {
  background: #fff;
  border: 1px solid #e4e9f2;
  border-radius: 10px;
  padding: 14px 16px;
}

.stat span {
  display: block;
  color: #66758a;
  font-size: 12px;
  margin-bottom: 4px;
}

.stat strong {
  font-size: 22px;
  font-weight: 600;
}
</style>
