<script setup>
import { useComplianceStore } from '../../stores/compliance'

const store = useComplianceStore()

const TYPE_LABELS = {
  payment: '付款',
  deposit: '押金',
  delivery: '交付',
  expiry: '到期',
  notice: '通知',
  termination: '终止',
  other: '其他',
}
const TYPE_COLORS = {
  payment: '#3498db',
  deposit: '#2459a9',
  delivery: '#16a085',
  expiry: '#8e44ad',
  notice: '#f39c12',
  termination: '#7f8c8d',
  other: '#9aabbe',
}

const FILTERS = [
  { key: 'pending', label: '待履行' },
  { key: 'overdue', label: '已逾期' },
  { key: 'review', label: '待确认' },
  { key: 'done', label: '已完成' },
  { key: 'all', label: '全部' },
]

function countdownText(m) {
  if (m.due_date == null) return '待确认'
  const d = m.days_left
  if (m.status !== 'pending') return '—'
  if (d == null) return '待确认'
  if (d < 0) return `已逾期 ${-d} 天`
  if (d === 0) return '今天截止'
  if (d === 1) return '明天截止'
  return `剩余 ${d} 天`
}

function countdownColor(m) {
  const d = m.days_left
  if (m.status !== 'pending' || d == null) return '#9aabbe'
  if (d < 0 || d === 0) return '#e74c3c'
  if (d <= 7) return '#f39c12'
  return '#3498db'
}

async function onDueChange(m, value) {
  await store.setDueDate(m.id, value || '')
}
</script>

<template>
  <div class="table-wrap">
    <div class="table-head">
      <el-radio-group v-model="store.milestoneFilter" size="small">
        <el-radio-button v-for="f in FILTERS" :key="f.key" :value="f.key">
          {{ f.label }}
        </el-radio-button>
      </el-radio-group>
      <span class="total">共 {{ store.visibleMilestones.length }} 项</span>
    </div>

    <el-table :data="store.visibleMilestones" style="width: 100%" row-key="id">
      <el-table-column label="履约节点" min-width="260">
        <template #default="{ row }">
          <div class="node-cell">
            <div class="node-title">
              {{ row.title }}
              <el-tag
                v-if="row.recurring !== 'none'"
                size="small"
                type="info"
                class="instance-tag"
              >第 {{ row.instance_index + 1 }} 期</el-tag>
            </div>
            <div v-if="row.description" class="node-desc">{{ row.description }}</div>
            <el-tooltip :content="row.clause_text" placement="top" :show-after="300">
              <span class="node-ref">{{ row.clause_ref || '—' }}</span>
            </el-tooltip>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="类型" width="90">
        <template #default="{ row }">
          <el-tag size="small" :color="TYPE_COLORS[row.node_type]" class="type-tag">
            {{ TYPE_LABELS[row.node_type] || row.node_type }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="截止日期" width="170">
        <template #default="{ row }">
          <el-date-picker
            v-if="row.needs_review === 1"
            :model-value="row.due_date"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="点击补录日期"
            size="small"
            style="width: 140px"
            @update:model-value="(v) => onDueChange(row, v)"
          />
          <el-date-picker
            v-else
            :model-value="row.due_date"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="待确认"
            size="small"
            style="width: 140px"
            :clearable="true"
            @update:model-value="(v) => onDueChange(row, v)"
          />
        </template>
      </el-table-column>

      <el-table-column label="倒计时" width="110">
        <template #default="{ row }">
          <span class="countdown" :style="{ color: countdownColor(row) }">
            {{ countdownText(row) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag v-if="row.status === 'done'" size="small" type="success">已完成</el-tag>
          <el-tag v-else-if="row.status === 'skipped'" size="small" type="info">已跳过</el-tag>
          <el-tag v-else size="small" type="warning">待履行</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.status === 'pending'"
            text
            size="small"
            type="success"
            @click="store.setMilestoneStatus(row.id, 'done')"
          >标记完成</el-button>
          <el-button
            v-else
            text
            size="small"
            @click="store.setMilestoneStatus(row.id, 'pending')"
          >恢复</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.table-wrap {
  background: #fff;
  border: 1px solid #e4e9f2;
  border-radius: 10px;
  padding: 14px;
}

.table-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.total {
  font-size: 12px;
  color: #9aabbe;
}

.node-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.node-title {
  font-weight: 600;
  color: #1d2b4f;
  display: flex;
  align-items: center;
  gap: 6px;
}

.instance-tag {
  font-weight: 400;
}

.node-desc {
  font-size: 12px;
  color: #66758a;
}

.node-ref {
  font-size: 12px;
  color: #9aabbe;
  cursor: help;
  width: fit-content;
}

.type-tag {
  color: #fff;
  border: none;
}

.countdown {
  font-weight: 600;
  font-size: 13px;
}
</style>
